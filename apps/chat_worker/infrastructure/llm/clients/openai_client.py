"""OpenAI LLM Client - LLMClientPort 구현체.

순수 LLM API 호출만 담당합니다.
비즈니스 로직(의도 분류, 답변 생성)은 Service Layer에서 담당.

Port: application/ports/llm/llm_client.py

Structured Output 지원:
- Primary: Agents SDK (Agent + output_type + Runner.run)
- Fallback: Responses API (text.format json_schema)

Agents SDK (Primary - web_search):
- https://openai.github.io/openai-agents-python/ref/tool/#agents.tool.WebSearchTool
- Agent + Runner.run_streamed() + WebSearchTool

Responses API (Fallback - web_search):
- https://platform.openai.com/docs/api-reference/responses
- tools: [{"type": "web_search", ...}]

Function Calling 지원:
- https://platform.openai.com/docs/guides/function-calling
- Chat Completions API의 tools/tool_choice 파라미터 사용
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Any, TypeVar

import httpx
from openai import AsyncOpenAI
from pydantic import BaseModel

from chat_worker.application.ports.llm import LLMClientPort
from chat_worker.infrastructure.llm.config import (
    HTTP_LIMITS,
    HTTP_TIMEOUT,
    MAX_RETRIES,
)
from chat_worker.infrastructure.telemetry import (
    is_langsmith_enabled,
    track_token_usage,
)

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class OpenAILLMClient(LLMClientPort):
    """OpenAI GPT 클라이언트.

    LLMClientPort 구현체로 순수 LLM 호출만 담당.
    비즈니스 로직은 Service에서:
    - IntentClassifier
    - AnswerGeneratorService
    """

    def __init__(
        self,
        model: str = "gpt-5.2",
        api_key: str | None = None,
    ):
        """초기화.

        Args:
            model: 모델 이름
            api_key: API 키 (None이면 환경변수 사용)
        """
        http_client = httpx.AsyncClient(
            timeout=HTTP_TIMEOUT,
            limits=HTTP_LIMITS,
        )
        self._client = AsyncOpenAI(
            api_key=api_key,
            http_client=http_client,
            max_retries=MAX_RETRIES,
        )
        self._model = model
        logger.info("OpenAILLMClient initialized", extra={"model": model})

    async def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        context: dict[str, Any] | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> str:
        """텍스트 생성."""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        user_content = prompt
        if context:
            context_str = json.dumps(context, ensure_ascii=False, indent=2)
            user_content = f"## Context\n{context_str}\n\n## Question\n{prompt}"

        messages.append({"role": "user", "content": user_content})

        # API 호출 파라미터
        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
        }
        if max_tokens is not None:
            kwargs["max_completion_tokens"] = max_tokens
        if temperature is not None:
            kwargs["temperature"] = temperature

        response = await self._client.chat.completions.create(**kwargs)

        # LangSmith 토큰 추적
        if is_langsmith_enabled() and response.usage:
            try:
                from langsmith.run_helpers import get_current_run_tree

                run_tree = get_current_run_tree()
                if run_tree:
                    track_token_usage(
                        run_tree=run_tree,
                        model=self._model,
                        input_tokens=response.usage.prompt_tokens,
                        output_tokens=response.usage.completion_tokens,
                    )
            except Exception as e:
                logger.debug("Failed to track token usage: %s", e)

        return response.choices[0].message.content or ""

    async def generate_stream(
        self,
        prompt: str,
        system_prompt: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> AsyncIterator[str]:
        """스트리밍 텍스트 생성."""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        user_content = prompt
        if context:
            context_str = json.dumps(context, ensure_ascii=False, indent=2)
            user_content = f"## Context\n{context_str}\n\n## Question\n{prompt}"

        messages.append({"role": "user", "content": user_content})

        stream = await self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            stream=True,
        )

        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    async def generate_structured(
        self,
        prompt: str,
        response_schema: type[T],
        system_prompt: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> T:
        """구조화된 응답 생성.

        Primary: Agents SDK (Agent + output_type + Runner.run)
        Fallback: Responses API (text.format json_schema)

        Args:
            prompt: 사용자 프롬프트
            response_schema: Pydantic BaseModel 서브클래스
            system_prompt: 시스템 프롬프트
            max_tokens: 최대 토큰 수
            temperature: 생성 온도

        Returns:
            response_schema 타입의 인스턴스
        """
        # Primary: Agents SDK
        try:
            return await self._structured_with_agents_sdk(prompt, response_schema, system_prompt)
        except Exception as e:
            logger.warning(
                "Agents SDK structured output failed, falling back to Responses API",
                extra={"error": str(e), "schema": response_schema.__name__},
            )

        # Fallback: Responses API
        return await self._structured_with_responses_api(
            prompt, response_schema, system_prompt, max_tokens, temperature
        )

    async def _structured_with_agents_sdk(
        self,
        prompt: str,
        response_schema: type[T],
        system_prompt: str | None = None,
    ) -> T:
        """Agents SDK로 구조화된 응답 생성 (Primary)."""
        from agents import Agent, Runner, RunConfig
        from agents.models.openai_responses import OpenAIResponsesModel

        agent = Agent(
            name="structured_output_agent",
            instructions=system_prompt or "",
            model=OpenAIResponsesModel(
                model=self._model,
                openai_client=self._client,
            ),
            output_type=response_schema,
        )

        result = await Runner.run(
            agent,
            input=prompt,
            run_config=RunConfig(tracing_disabled=True),
        )

        logger.debug(
            "Structured output generated (Agents SDK)",
            extra={"schema": response_schema.__name__},
        )
        return result.final_output

    async def _structured_with_responses_api(
        self,
        prompt: str,
        response_schema: type[T],
        system_prompt: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> T:
        """Responses API로 구조화된 응답 생성 (Fallback)."""
        input_messages: list[dict[str, str]] = []
        if system_prompt:
            input_messages.append({"role": "developer", "content": system_prompt})
        input_messages.append({"role": "user", "content": prompt})

        kwargs: dict[str, Any] = {
            "model": self._model,
            "input": input_messages,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": response_schema.__name__,
                    "schema": response_schema.model_json_schema(),
                    "strict": True,
                },
            },
        }
        if max_tokens is not None:
            kwargs["max_output_tokens"] = max_tokens
        if temperature is not None:
            kwargs["temperature"] = temperature

        try:
            response = await self._client.responses.create(**kwargs)
            content = response.output_text or "{}"

            data = json.loads(content)
            result = response_schema.model_validate(data)

            logger.debug(
                "Structured output generated (Responses API)",
                extra={"schema": response_schema.__name__},
            )
            return result

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse structured response: {e}")
            raise ValueError(f"Invalid JSON response: {e}") from e
        except Exception as e:
            logger.error(f"Structured output generation failed: {e}")
            raise

    async def generate_with_tools(
        self,
        prompt: str,
        tools: list[str],
        system_prompt: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> AsyncIterator[str]:
        """네이티브 도구를 사용한 스트리밍 생성.

        Primary: OpenAI Agents SDK (WebSearchTool + Runner.run_streamed)
        Fallback: Responses API (tools: [{"type": "web_search"}])

        Args:
            prompt: 사용자 프롬프트
            tools: 사용할 도구 목록 (예: ["web_search"])
            system_prompt: 시스템 프롬프트
            context: 추가 컨텍스트 (JSON으로 변환)

        Yields:
            생성된 텍스트 청크
        """
        user_content = prompt
        if context:
            context_str = json.dumps(context, ensure_ascii=False, indent=2)
            user_content = f"## Context\n{context_str}\n\n## Question\n{prompt}"

        # Primary: Agents SDK
        try:
            async for chunk in self._generate_with_agents_sdk(user_content, tools, system_prompt):
                yield chunk
            return
        except Exception as e:
            logger.warning(
                "Agents SDK failed, falling back to Responses API",
                extra={"error": str(e), "model": self._model, "tools": tools},
            )

        # Fallback: Responses API
        async for chunk in self._generate_with_responses_api(user_content, tools, system_prompt):
            yield chunk

    async def _generate_with_agents_sdk(
        self,
        user_content: str,
        tools: list[str],
        system_prompt: str | None = None,
    ) -> AsyncIterator[str]:
        """Agents SDK로 도구 사용 스트리밍 생성 (Primary).

        Agent + WebSearchTool + Runner.run_streamed()
        """
        from agents import Agent, Runner, RunConfig, WebSearchTool
        from agents.models.openai_responses import OpenAIResponsesModel
        from openai.types.responses import ResponseTextDeltaEvent

        # WebSearchTool 설정
        agent_tools = []
        for tool in tools:
            if tool == "web_search":
                agent_tools.append(WebSearchTool(search_context_size="medium"))

        agent = Agent(
            name="web_search_agent",
            instructions=system_prompt or "",
            model=OpenAIResponsesModel(
                model=self._model,
                openai_client=self._client,
            ),
            tools=agent_tools,
        )

        result = Runner.run_streamed(
            agent,
            input=user_content,
            run_config=RunConfig(tracing_disabled=True),
        )

        async for event in result.stream_events():
            if (
                event.type == "raw_response_event"
                and isinstance(event.data, ResponseTextDeltaEvent)
                and event.data.delta
            ):
                yield event.data.delta

    async def _generate_with_responses_api(
        self,
        user_content: str,
        tools: list[str],
        system_prompt: str | None = None,
    ) -> AsyncIterator[str]:
        """Responses API로 도구 사용 스트리밍 생성 (Fallback).

        client.responses.create() + tools: [{"type": "web_search"}]
        """
        input_messages: list[dict[str, str]] = []
        if system_prompt:
            input_messages.append({"role": "developer", "content": system_prompt})
        input_messages.append({"role": "user", "content": user_content})

        tool_configs: list[dict[str, Any]] = []
        for tool in tools:
            if tool == "web_search":
                tool_configs.append(
                    {
                        "type": "web_search",
                        "search_context_size": "medium",
                    }
                )

        try:
            response = await self._client.responses.create(
                model=self._model,
                input=input_messages,
                tools=tool_configs if tool_configs else None,
                stream=True,
            )

            async for event in response:
                if hasattr(event, "type") and event.type == "response.output_text.delta":
                    if hasattr(event, "delta") and event.delta:
                        yield event.delta

        except Exception as e:
            logger.error(
                "Responses API fallback failed",
                extra={"error": str(e), "model": self._model, "tools": tools},
            )
            raise

    async def generate_function_call(
        self,
        prompt: str,
        functions: list[dict[str, Any]],
        system_prompt: str | None = None,
        function_call: str | dict[str, str] = "auto",
    ) -> tuple[str | None, dict[str, Any] | None]:
        """Function Calling API 호출 (OpenAI Chat Completions).

        OpenAI의 Function Calling 기능을 사용하여 LLM이 어떤 함수를
        어떤 인자로 호출해야 할지 결정하도록 합니다.

        Args:
            prompt: 사용자 메시지
            functions: OpenAI function definitions 리스트
            system_prompt: 시스템 프롬프트 (선택)
            function_call: 함수 호출 제어 ("auto", "none", {"name": "..."})

        Returns:
            (function_name, arguments) 튜플
            - function_name: 호출할 함수 이름 (None이면 함수 호출 안함)
            - arguments: 함수 인자 dict (JSON 파싱됨)

        Raises:
            ValueError: JSON 파싱 실패 시
        """
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        try:
            # functions → tools 변환
            tools = [{"type": "function", "function": func} for func in functions]

            # function_call → tool_choice 변환
            tool_choice: str | dict[str, Any] = "auto"
            if function_call == "none":
                tool_choice = "none"
            elif isinstance(function_call, dict) and "name" in function_call:
                tool_choice = {
                    "type": "function",
                    "function": {"name": function_call["name"]},
                }

            response = await self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                tools=tools,
                tool_choice=tool_choice,
            )

            message = response.choices[0].message

            # tool_calls 결과 확인 (modern API)
            if message.tool_calls:
                tool_call = message.tool_calls[0]
                func_name = tool_call.function.name
                func_args_str = tool_call.function.arguments

                # JSON 파싱
                try:
                    func_args = json.loads(func_args_str)
                except json.JSONDecodeError as e:
                    logger.error(
                        f"Failed to parse function arguments: {e}",
                        extra={
                            "function_name": func_name,
                            "arguments_str": func_args_str,
                        },
                    )
                    raise ValueError(f"Invalid function arguments JSON: {e}") from e

                logger.debug(
                    "Function call generated",
                    extra={
                        "function_name": func_name,
                        "arguments": func_args,
                    },
                )
                return (func_name, func_args)

            # Function call이 없는 경우
            logger.debug("No function call generated")
            return (None, None)

        except Exception as e:
            logger.error(f"generate_function_call failed: {e}")
            raise
