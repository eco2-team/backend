"""News Source Port.

뉴스 소스 추상화 인터페이스.
네이버, NewsData.io 등 다양한 뉴스 소스 어댑터 구현 가능.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from info.domain.entities import NewsArticle


class NewsSourcePort(ABC):
    """뉴스 소스 포트.

    외부 뉴스 API에서 기사를 가져오는 인터페이스.
    """

    @property
    @abstractmethod
    def source_name(self) -> str:
        """소스 식별자 (예: "naver", "newsdata")."""
        pass

    @abstractmethod
    async def fetch_news(
        self,
        query: str,
        max_results: int = 50,
    ) -> list[NewsArticle]:
        """뉴스 검색.

        Args:
            query: 검색어
            max_results: 최대 결과 수

        Returns:
            뉴스 기사 목록
        """
        pass

    async def close(self) -> None:
        """리소스 정리 (optional)."""
        pass
