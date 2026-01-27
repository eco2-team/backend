"""Google Gemini Client - LLMClientPort 구현체.

순수 LLM API 호출만 담당합니다.
비즈니스 로직(의도 분류, 답변 생성)은 Service Layer에서 담당.

Port: application/ports/llm/llm_client.py

Structured Output 지원:
- https://ai.google.dev/gemini-api/docs/structured-output

Function Calling 지원:
- https://ai.google.dev/gemini-api/docs/function-calling

SDK 버전: google-genai >= 1.60.0
- FunctionCallingConfigMode enum 사용
- allowed_function_names 지원
- system_instruction 필드 사용
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import AsyncIterator
from typing import Any, TypeVar

from google import genai
from google.genai import types
from pydantic import BaseModel

from chat_worker.application.ports.llm import LLMClientPort
from chat_worker.infrastructure.llm.config import MODEL_CONTEXT_WINDOWS
from chat_worker.infrastructure.telemetry import (
    is_langsmith_enabled,
    track_token_usage,
)

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class GeminiLLMClient(LLMClientPort):
    """Google Gemini 클라이언트.

    LLMClientPort 구현체로 순수 LLM 호출만 담당.
    비즈니스 로직은 Service에서:
    - IntentClassifier
    - AnswerGeneratorService
    """

    def __init__(
        self,
        model: str = "gemini-3-flash-preview",
        api_key: str | None = None,
    ):
        """초기화.

        Args:
            model: 모델 이름
            api_key: API 키 (None이면 환경변수 사용)
        """
        key = api_key or os.getenv("GOOGLE_API_KEY")
        self._client = genai.Client(api_key=key) if key else genai.Client()
        self._model = model
        self._max_context = MODEL_CONTEXT_WINDOWS.get(model, 1_000_000)
        logger.info("GeminiLLMClient initialized", extra={"model": model})

    async def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        context: dict[str, Any] | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> str:
        """텍스트 생성.

        google-genai 1.60.0: system_instruction 필드로 시스템 프롬프트 분리.
        """
        # 사용자 프롬프트 구성
        user_content = ""
        if context:
            context_str = json.dumps(context, ensure_ascii=False, indent=2)
            user_content = f"## Context\n{context_str}\n\n"
        user_content += f"## Question\n{prompt}"

        # GenerateContentConfig 구성
        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            max_output_tokens=max_tokens,
            temperature=temperature,
        )

        response = await self._client.aio.models.generate_content(
            model=self._model,
            contents=user_content,
            config=config,
        )

        # LangSmith 토큰 추적
        if is_langsmith_enabled() and response.usage_metadata:
            try:
                from langsmith.run_helpers import get_current_run_tree

                run_tree = get_current_run_tree()
                if run_tree:
                    track_token_usage(
                        run_tree=run_tree,
                        model=self._model,
                        input_tokens=response.usage_metadata.prompt_token_count,
                        output_tokens=response.usage_metadata.candidates_token_count,
                    )
            except Exception as e:
                logger.debug("Failed to track token usage: %s", e)

        return response.text or ""

    async def generate_stream(
        self,
        prompt: str,
        system_prompt: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> AsyncIterator[str]:
        """스트리밍 텍스트 생성.

        google-genai 1.60.0: system_instruction 필드로 시스템 프롬프트 분리.
        """
        user_content = ""
        if context:
            context_str = json.dumps(context, ensure_ascii=False, indent=2)
            user_content = f"## Context\n{context_str}\n\n"
        user_content += f"## Question\n{prompt}"

        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
        )

        response = await self._client.aio.models.generate_content_stream(
            model=self._model,
            contents=user_content,
            config=config,
        )
        # 마지막 청크에서 토큰 사용량 캡처
        last_usage = None
        async for chunk in response:
            if chunk.text:
                yield chunk.text
            # usage_metadata는 마지막 청크에 포함
            if chunk.usage_metadata:
                last_usage = chunk.usage_metadata

        # 스트리밍 완료 후 LangSmith에 토큰 사용량 보고
        if is_langsmith_enabled() and last_usage:
            try:
                from langsmith.run_helpers import get_current_run_tree

                run_tree = get_current_run_tree()
                if run_tree:
                    track_token_usage(
                        run_tree=run_tree,
                        model=self._model,
                        input_tokens=last_usage.prompt_token_count or 0,
                        output_tokens=last_usage.candidates_token_count or 0,
                    )
            except ImportError:
                pass

    async def generate_with_tools(
        self,
        prompt: str,
        tools: list[str],
        system_prompt: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> AsyncIterator[str]:
        """도구를 사용한 텍스트 생성 (Google Search Grounding).

        google-genai 1.60.0: system_instruction 필드로 시스템 프롬프트 분리.

        Args:
            prompt: 사용자 프롬프트
            tools: 사용할 도구 목록 (예: ["web_search"])
            system_prompt: 시스템 프롬프트
            context: 추가 컨텍스트
        """
        tool_configs = []
        for tool in tools:
            if tool == "web_search":
                tool_configs.append(types.Tool(google_search=types.GoogleSearch()))

        user_content = ""
        if context:
            context_str = json.dumps(context, ensure_ascii=False, indent=2)
            user_content = f"## Context\n{context_str}\n\n"
        user_content += f"## Question\n{prompt}"

        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            tools=tool_configs if tool_configs else None,
        )

        try:
            response = await self._client.aio.models.generate_content_stream(
                model=self._model,
                contents=user_content,
                config=config,
            )
            # 마지막 청크에서 토큰 사용량 캡처
            last_usage = None
            async for chunk in response:
                if chunk.text:
                    yield chunk.text
                if chunk.usage_metadata:
                    last_usage = chunk.usage_metadata

            # 스트리밍 완료 후 LangSmith에 토큰 사용량 보고
            if is_langsmith_enabled() and last_usage:
                try:
                    from langsmith.run_helpers import get_current_run_tree

                    run_tree = get_current_run_tree()
                    if run_tree:
                        track_token_usage(
                            run_tree=run_tree,
                            model=self._model,
                            input_tokens=last_usage.prompt_token_count or 0,
                            output_tokens=last_usage.candidates_token_count or 0,
                        )
                except ImportError:
                    pass
        except Exception as e:
            logger.warning(f"generate_with_tools failed, falling back to plain: {e}")
            async for chunk in self.generate_stream(
                prompt=prompt,
                system_prompt=system_prompt,
                context=context,
            ):
                yield chunk

    async def generate_function_call(
        self,
        prompt: str,
        functions: list[dict[str, Any]],
        system_prompt: str | None = None,
        function_call: str | dict[str, str] = "auto",
    ) -> tuple[str, dict[str, Any] | None]:
        """Function Calling (Gemini 네이티브).

        google-genai 1.60.0:
        - FunctionCallingConfigMode enum 사용
        - allowed_function_names 지원 (특정 함수 강제)
        - system_instruction 필드 사용

        Args:
            prompt: 사용자 프롬프트
            functions: OpenAI 형식의 function definitions
            system_prompt: 시스템 프롬프트
            function_call: 호출 모드 ("auto", "none", {"name": "func_name"})

        Returns:
            (function_name, arguments) 튜플
        """
        # OpenAI format → Gemini FunctionDeclaration
        function_declarations = []
        for func in functions:
            func_decl = types.FunctionDeclaration(
                name=func["name"],
                description=func.get("description", ""),
                parameters=func.get("parameters"),
            )
            function_declarations.append(func_decl)

        tool = types.Tool(function_declarations=function_declarations)

        # function_call mode 변환 (enum 사용)
        fc_mode = types.FunctionCallingConfigMode.AUTO
        allowed_names: list[str] | None = None

        if isinstance(function_call, dict) and "name" in function_call:
            fc_mode = types.FunctionCallingConfigMode.ANY
            allowed_names = [function_call["name"]]
        elif function_call == "none":
            fc_mode = types.FunctionCallingConfigMode.NONE

        function_calling_config = types.FunctionCallingConfig(
            mode=fc_mode,
            allowed_function_names=allowed_names,
        )

        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            tools=[tool],
            tool_config=types.ToolConfig(
                function_calling_config=function_calling_config,
            ),
        )

        response = await self._client.aio.models.generate_content(
            model=self._model,
            contents=prompt,
            config=config,
        )

        # LangSmith 토큰 추적
        if is_langsmith_enabled() and response.usage_metadata:
            try:
                from langsmith.run_helpers import get_current_run_tree

                run_tree = get_current_run_tree()
                if run_tree:
                    track_token_usage(
                        run_tree=run_tree,
                        model=self._model,
                        input_tokens=response.usage_metadata.prompt_token_count or 0,
                        output_tokens=response.usage_metadata.candidates_token_count or 0,
                    )
            except ImportError:
                pass

        # Function call 결과 추출
        if response.candidates:
            for part in response.candidates[0].content.parts:
                if part.function_call:
                    func_name = part.function_call.name
                    func_args = dict(part.function_call.args) if part.function_call.args else {}
                    return (func_name, func_args)

        return ("", None)

    async def generate_structured(
        self,
        prompt: str,
        response_schema: type[T],
        system_prompt: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> T:
        """구조화된 응답 생성 (Gemini Structured Output).

        google-genai 1.60.0: system_instruction 필드로 시스템 프롬프트 분리.

        Gemini의 네이티브 Structured Output API를 사용하여
        JSON 스키마를 준수하는 응답을 보장합니다.

        Args:
            prompt: 사용자 프롬프트
            response_schema: Pydantic BaseModel 서브클래스
            system_prompt: 시스템 프롬프트
            max_tokens: 최대 토큰 수
            temperature: 생성 온도

        Returns:
            response_schema 타입의 인스턴스
        """
        user_content = f"## Question\n{prompt}"

        # GenerateContentConfig 구성
        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            response_mime_type="application/json",
            response_schema=response_schema,
            max_output_tokens=max_tokens,
            temperature=temperature,
        )

        try:
            response = await self._client.aio.models.generate_content(
                model=self._model,
                contents=user_content,
                config=config,
            )

            # LangSmith 토큰 추적
            if is_langsmith_enabled() and response.usage_metadata:
                try:
                    from langsmith.run_helpers import get_current_run_tree

                    run_tree = get_current_run_tree()
                    if run_tree:
                        track_token_usage(
                            run_tree=run_tree,
                            model=self._model,
                            input_tokens=response.usage_metadata.prompt_token_count or 0,
                            output_tokens=response.usage_metadata.candidates_token_count or 0,
                        )
                except ImportError:
                    pass

            # 빈 응답 또는 공백만 있는 응답 처리
            content = (response.text or "").strip() or "{}"

            # JSON 파싱 및 Pydantic 검증
            data = json.loads(content)
            result = response_schema.model_validate(data)

            logger.debug(
                "Structured output generated",
                extra={"schema": response_schema.__name__},
            )
            return result

        except json.JSONDecodeError as e:
            logger.error(
                "Failed to parse structured response",
                extra={
                    "error": str(e),
                    "content_preview": content[:100] if content else "(empty)",
                    "schema": response_schema.__name__,
                },
            )
            raise ValueError(f"Invalid JSON response: {e}") from e
        except Exception as e:
            logger.error(
                "Structured output generation failed",
                extra={"error": str(e), "schema": response_schema.__name__},
            )
            raise
