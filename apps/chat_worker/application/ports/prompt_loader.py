"""Prompt Loader Port - 프롬프트 로딩 추상화.

Application Layer에서 프롬프트를 로드할 때 사용하는 Port입니다.
Infrastructure의 파일 시스템 접근을 추상화합니다.

Clean Architecture:
- Port: 이 파일 (추상화, Application Layer)
- Adapter: infrastructure/assets/prompt_loader.py (구현체)
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class PromptLoaderPort(ABC):
    """프롬프트 로더 Port.

    Application Layer에서 프롬프트 파일을 로드할 때 사용합니다.
    구현체는 Infrastructure Layer에서 제공합니다.
    """

    @abstractmethod
    def load(self, category: str, name: str) -> str:
        """프롬프트 파일 로드.

        Args:
            category: 프롬프트 카테고리 (classification, extraction, evaluation 등)
            name: 프롬프트 이름 (확장자 제외)

        Returns:
            프롬프트 내용

        Raises:
            FileNotFoundError: 파일이 없을 경우
        """
        pass

    def load_or_default(self, category: str, name: str, default: str) -> str:
        """프롬프트 파일 로드 (기본값 지원).

        Args:
            category: 프롬프트 카테고리
            name: 프롬프트 이름
            default: 파일이 없을 경우 반환할 기본값

        Returns:
            프롬프트 내용 또는 기본값
        """
        try:
            return self.load(category, name)
        except FileNotFoundError:
            return default
