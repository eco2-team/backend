"""Google Gemini Client - LLMClientPort 구현체.

순수 LLM API 호출만 담당합니다.
비즈니스 로직(의도 분류, 답변 생성)은 Service Layer에서 담당.

Port: application/ports/llm/llm_client.py

Structured Output 지원:
- https://ai.google.dev/gemini-api/docs/structured-output

Function Calling 지원:
- https://ai.google.dev/gemini-api/docs/function-calling
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import AsyncIterator
from typing import Any, TypeVar

from google import genai
from pydantic import BaseModel

from chat_worker.application.ports.llm import LLMClientPort
from chat_worker.infrastructure.llm.config import MODEL_CONTEXT_WINDOWS

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
        """텍스트 생성."""
        full_prompt = ""
        if system_prompt:
            full_prompt = f"{system_prompt}\n\n"
        if context:
            context_str = json.dumps(context, ensure_ascii=False, indent=2)
            full_prompt += f"## Context\n{context_str}\n\n"
        full_prompt += f"## Question\n{prompt}"

        # API 호출 파라미터
        config = {}
        if max_tokens is not None:
            config["max_output_tokens"] = max_tokens
        if temperature is not None:
            config["temperature"] = temperature

        response = await self._client.aio.models.generate_content(
            model=self._model,
            contents=full_prompt,
            config=config if config else None,
        )
        return response.text or ""

    async def generate_stream(
        self,
        prompt: str,
        system_prompt: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> AsyncIterator[str]:
        """스트리밍 텍스트 생성."""
        full_prompt = ""
        if system_prompt:
            full_prompt = f"{system_prompt}\n\n"
        if context:
            context_str = json.dumps(context, ensure_ascii=False, indent=2)
            full_prompt += f"## Context\n{context_str}\n\n"
        full_prompt += f"## Question\n{prompt}"

        response = await self._client.aio.models.generate_content_stream(
            model=self._model,
            contents=full_prompt,
        )
        async for chunk in response:
            if chunk.text:
                yield chunk.text

    async def generate_structured(
        self,
        prompt: str,
        response_schema: type[T],
        system_prompt: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> T:
        """구조화된 응답 생성 (Gemini Structured Output).

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
        full_prompt = ""
        if system_prompt:
            full_prompt = f"{system_prompt}\n\n"
        full_prompt += f"## Question\n{prompt}"

        # API 호출 파라미터
        config: dict[str, Any] = {
            "response_mime_type": "application/json",
            "response_schema": response_schema,
        }
        if max_tokens is not None:
            config["max_output_tokens"] = max_tokens
        if temperature is not None:
            config["temperature"] = temperature

        try:
            response = await self._client.aio.models.generate_content(
                model=self._model,
                contents=full_prompt,
                config=config,
            )
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

    async def generate_function_call(
        self,
        prompt: str,
        functions: list[dict[str, Any]],
        system_prompt: str | None = None,
        function_call: str | dict[str, str] = "auto",
    ) -> tuple[str | None, dict[str, Any] | None]:
        """Function Calling API 호출 (Gemini).

        Gemini의 Function Calling 기능을 사용하여 LLM이 어떤 함수를
        어떤 인자로 호출해야 할지 결정하도록 합니다.

        Args:
            prompt: 사용자 메시지
            functions: OpenAI 호환 function definitions 리스트
            system_prompt: 시스템 프롬프트 (선택)
            function_call: 함수 호출 제어 ("auto", "none", {"name": "..."})

        Returns:
            (function_name, arguments) 튜플
            - function_name: 호출할 함수 이름 (None이면 함수 호출 안함)
            - arguments: 함수 인자 dict

        Raises:
            ValueError: 응답 파싱 실패 시
        """
        from google.genai import types

        # OpenAI 포맷 → Gemini 포맷 변환
        function_declarations = []
        for func in functions:
            # parameters 스키마 변환
            params = func.get("parameters", {})
            properties = params.get("properties", {})
            required = params.get("required", [])

            # Gemini Schema 형식으로 변환
            schema_properties = {}
            for prop_name, prop_def in properties.items():
                prop_type = prop_def.get("type", "string").upper()
                schema_properties[prop_name] = types.Schema(
                    type=prop_type,
                    description=prop_def.get("description", ""),
                )

            function_declarations.append(
                types.FunctionDeclaration(
                    name=func["name"],
                    description=func.get("description", ""),
                    parameters=types.Schema(
                        type="OBJECT",
                        properties=schema_properties,
                        required=required,
                    ),
                )
            )

        tools = [types.Tool(function_declarations=function_declarations)]

        # 프롬프트 구성
        full_prompt = ""
        if system_prompt:
            full_prompt = f"{system_prompt}\n\n"
        full_prompt += prompt

        # tool_config 설정
        tool_config = None
        if function_call == "none":
            tool_config = types.ToolConfig(
                function_calling_config=types.FunctionCallingConfig(mode="NONE")
            )
        elif isinstance(function_call, dict) and "name" in function_call:
            tool_config = types.ToolConfig(
                function_calling_config=types.FunctionCallingConfig(
                    mode="ANY",
                    allowed_function_names=[function_call["name"]],
                )
            )
        # "auto"는 기본값이므로 별도 설정 불필요

        try:
            response = await self._client.aio.models.generate_content(
                model=self._model,
                contents=full_prompt,
                config={
                    "tools": tools,
                    "tool_config": tool_config,
                },
            )

            # Function call 결과 확인
            if response.candidates and response.candidates[0].content.parts:
                for part in response.candidates[0].content.parts:
                    if hasattr(part, "function_call") and part.function_call:
                        func_call = part.function_call
                        func_name = func_call.name
                        func_args = dict(func_call.args) if func_call.args else {}

                        logger.debug(
                            "Function call generated",
                            extra={
                                "function_name": func_name,
                                "arguments": func_args,
                            },
                        )
                        return (func_name, func_args)

            # Function call이 없는 경우 (일반 응답)
            logger.debug("No function call generated")
            return (None, None)

        except Exception as e:
            logger.error(
                "generate_function_call failed",
                extra={"error": str(e)},
            )
            raise
