"""Prompt Builder Port.

프롬프트 빌드 추상화 - Application Layer가 Infrastructure에 의존하지 않도록.

Clean Architecture:
- Port: 이 파일 (추상화, Application Layer)
- Adapter: infrastructure/assets/prompt_loader.py (구현체, Infrastructure Layer)
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class PromptBuilderPort(ABC):
    """프롬프트 빌더 Port.

    Intent에 따라 시스템 프롬프트를 구성하는 인터페이스.
    Local Prompt Optimization 패턴 (arxiv:2504.20355) 지원.
    """

    @abstractmethod
    def build(self, intent: str) -> str:
        """단일 Intent에 대한 시스템 프롬프트 생성.

        Args:
            intent: Intent 타입 (waste/character/location/general 등)

        Returns:
            Global + Local 조합된 시스템 프롬프트
        """
        ...

    @abstractmethod
    def build_multi(self, intents: list[str]) -> str:
        """Multi-Intent에 대한 조합 프롬프트 생성.

        여러 Intent의 Local 프롬프트를 조합하여 하나의 시스템 프롬프트 생성.
        DialogUSR 패턴: 분해된 쿼리에 맞는 Policy를 조합 주입.

        Args:
            intents: Intent 타입 리스트 (예: ["waste", "character"])

        Returns:
            Global + 조합된 Local 프롬프트
        """
        ...
