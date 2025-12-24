"""OpenAI LLM Provider 구현."""

from __future__ import annotations

import logging
from typing import Any, TypeVar

from openai import AsyncOpenAI, OpenAI
from pydantic import BaseModel

from .base import ChatRequest, LLMProvider, VisionRequest
from .config import LLMConfig

logger = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)


class OpenAIProvider(LLMProvider):
    """OpenAI API Provider.

    GPT-5.1, GPT-4o 등 OpenAI 모델 지원.
    Vision API (responses.parse) 및 Chat Completion (chat.completions.parse) 지원.
    """

    def __init__(self, config: LLMConfig):
        self._config = config
        self._sync_client: OpenAI | None = None
        self._async_client: AsyncOpenAI | None = None

    @property
    def name(self) -> str:
        return "openai"

    @property
    def _client(self) -> OpenAI:
        if self._sync_client is None:
            self._sync_client = OpenAI(api_key=self._config.api_key)
        return self._sync_client

    @property
    def _aclient(self) -> AsyncOpenAI:
        if self._async_client is None:
            self._async_client = AsyncOpenAI(api_key=self._config.api_key)
        return self._async_client

    def vision_analyze_sync(
        self,
        request: VisionRequest,
        response_model: type[T],
    ) -> dict[str, Any]:
        """OpenAI Vision API 동기 호출."""
        system_items = []
        if request.system_prompt:
            system_items.append({"type": "input_text", "text": request.system_prompt})

        content_items = [
            {"type": "input_text", "text": request.prompt},
            {"type": "input_image", "image_url": request.image_url},
        ]

        logger.info(
            "OpenAI Vision sync call",
            extra={"model": self._config.vision_model},
        )

        response = self._client.responses.parse(
            model=self._config.vision_model,
            input=[
                {"role": "user", "content": content_items},
                {"role": "system", "content": system_items},
            ],
            text_format=response_model,
        )

        return response.output_parsed.model_dump()

    async def vision_analyze(
        self,
        request: VisionRequest,
        response_model: type[T],
    ) -> dict[str, Any]:
        """OpenAI Vision API 비동기 호출."""
        system_items = []
        if request.system_prompt:
            system_items.append({"type": "input_text", "text": request.system_prompt})

        content_items = [
            {"type": "input_text", "text": request.prompt},
            {"type": "input_image", "image_url": request.image_url},
        ]

        logger.info(
            "OpenAI Vision async call",
            extra={"model": self._config.vision_model},
        )

        response = await self._aclient.responses.parse(
            model=self._config.vision_model,
            input=[
                {"role": "user", "content": content_items},
                {"role": "system", "content": system_items},
            ],
            text_format=response_model,
        )

        return response.output_parsed.model_dump()

    def chat_completion_sync(
        self,
        request: ChatRequest,
        response_model: type[T],
    ) -> dict[str, Any]:
        """OpenAI Chat Completion 동기 호출."""
        messages = list(request.messages)
        if request.system_prompt:
            messages.insert(0, {"role": "system", "content": request.system_prompt})

        logger.info(
            "OpenAI Chat sync call",
            extra={"model": self._config.chat_model},
        )

        response = self._client.chat.completions.parse(
            model=self._config.chat_model,
            messages=messages,
            response_format=response_model,
        )

        return response.choices[0].message.parsed.model_dump()

    async def chat_completion(
        self,
        request: ChatRequest,
        response_model: type[T],
    ) -> dict[str, Any]:
        """OpenAI Chat Completion 비동기 호출."""
        messages = list(request.messages)
        if request.system_prompt:
            messages.insert(0, {"role": "system", "content": request.system_prompt})

        logger.info(
            "OpenAI Chat async call",
            extra={"model": self._config.chat_model},
        )

        response = await self._aclient.chat.completions.parse(
            model=self._config.chat_model,
            messages=messages,
            response_format=response_model,
        )

        return response.choices[0].message.parsed.model_dump()
