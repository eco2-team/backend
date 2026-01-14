"""LLM Client Port - 순수 LLM API 호출.

책임:
- 텍스트 생성 (generate)
- 스트리밍 생성 (generate_stream)

포함하지 않는 것 (LLMPolicy로 분리):
- 프롬프트 템플릿
- 모델 선택/라우팅
- 리트라이 정책
- 레이트리밋
"""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any


class LLMClientPort(ABC):
    """LLM 클라이언트 포트.

    순수 API 호출만 담당.
    OpenAI, Gemini 등 구현체를 DI로 주입.
    """

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        context: dict[str, Any] | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> str:
        """텍스트 생성.

        Args:
            prompt: 사용자 프롬프트
            system_prompt: 시스템 프롬프트
            context: 추가 컨텍스트 (JSON으로 변환)
            max_tokens: 최대 토큰 수
            temperature: 생성 온도

        Returns:
            생성된 텍스트
        """
        pass

    @abstractmethod
    async def generate_stream(
        self,
        prompt: str,
        system_prompt: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> AsyncIterator[str]:
        """스트리밍 텍스트 생성.

        Args:
            prompt: 사용자 프롬프트
            system_prompt: 시스템 프롬프트
            context: 추가 컨텍스트 (JSON으로 변환)

        Yields:
            생성된 텍스트 청크
        """
        pass
