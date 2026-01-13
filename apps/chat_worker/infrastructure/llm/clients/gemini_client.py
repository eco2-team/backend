"""Google Gemini Client - LLMClientPort 구현체.

순수 LLM API 호출만 담당합니다.
비즈니스 로직(의도 분류, 답변 생성)은 Service Layer에서 담당.

Port: application/ports/llm/llm_client.py
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import AsyncIterator
from typing import Any

from google import genai

from chat_worker.application.ports.llm import LLMClientPort
from chat_worker.infrastructure.llm.config import MODEL_CONTEXT_WINDOWS

logger = logging.getLogger(__name__)


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

        response = self._client.models.generate_content(
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

        response = self._client.models.generate_content_stream(
            model=self._model,
            contents=full_prompt,
        )
        for chunk in response:
            if chunk.text:
                yield chunk.text
