"""OpenAI LLM Client - LLMClientPort 구현체.

순수 LLM API 호출만 담당합니다.
비즈니스 로직(의도 분류, 답변 생성)은 Service Layer에서 담당.

Port: application/ports/llm/llm_client.py
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Any

import httpx
from openai import AsyncOpenAI

from chat_worker.application.ports.llm import LLMClientPort
from chat_worker.infrastructure.llm.config import (
    HTTP_LIMITS,
    HTTP_TIMEOUT,
    MAX_RETRIES,
)

logger = logging.getLogger(__name__)


class OpenAILLMClient(LLMClientPort):
    """OpenAI GPT 클라이언트.

    LLMClientPort 구현체로 순수 LLM 호출만 담당.
    비즈니스 로직은 Service에서:
    - IntentClassifier
    - AnswerGeneratorService
    """

    def __init__(
        self,
        model: str = "gpt-5.2-turbo",
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
            kwargs["max_tokens"] = max_tokens
        if temperature is not None:
            kwargs["temperature"] = temperature

        response = await self._client.chat.completions.create(**kwargs)
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
