"""LLM Provider 추상 인터페이스."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


@dataclass
class VisionRequest:
    """Vision API 요청 데이터."""

    image_url: str
    prompt: str
    system_prompt: str | None = None


@dataclass
class ChatRequest:
    """Chat Completion 요청 데이터."""

    messages: list[dict[str, str]]
    system_prompt: str | None = None


class LLMProvider(ABC):
    """LLM Provider 추상 베이스 클래스.

    OpenAI, Gemini 등 다양한 Provider를 통합 인터페이스로 제공.
    동기/비동기 메서드 모두 지원.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider 이름 (openai, gemini, etc.)."""
        ...

    @abstractmethod
    def vision_analyze_sync(
        self,
        request: VisionRequest,
        response_model: type[T],
    ) -> dict[str, Any]:
        """이미지 분석 (동기)."""
        ...

    @abstractmethod
    async def vision_analyze(
        self,
        request: VisionRequest,
        response_model: type[T],
    ) -> dict[str, Any]:
        """이미지 분석 (비동기)."""
        ...

    @abstractmethod
    def chat_completion_sync(
        self,
        request: ChatRequest,
        response_model: type[T],
    ) -> dict[str, Any]:
        """채팅 완성 (동기)."""
        ...

    @abstractmethod
    async def chat_completion(
        self,
        request: ChatRequest,
        response_model: type[T],
    ) -> dict[str, Any]:
        """채팅 완성 (비동기)."""
        ...
