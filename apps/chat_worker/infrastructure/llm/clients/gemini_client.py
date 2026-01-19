"""Google Gemini Client - LLMClientPort 구현체.

순수 LLM API 호출만 담당합니다.
비즈니스 로직(의도 분류, 답변 생성)은 Service Layer에서 담당.

Port: application/ports/llm/llm_client.py

Structured Output 지원:
- https://ai.google.dev/gemini-api/docs/structured-output
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
            content = response.text or "{}"

            # JSON 파싱 및 Pydantic 검증
            data = json.loads(content)
            result = response_schema.model_validate(data)

            logger.debug(
                "Structured output generated",
                extra={"schema": response_schema.__name__},
            )
            return result

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse structured response: {e}")
            raise ValueError(f"Invalid JSON response: {e}") from e
        except Exception as e:
            logger.error(f"Structured output generation failed: {e}")
            raise
