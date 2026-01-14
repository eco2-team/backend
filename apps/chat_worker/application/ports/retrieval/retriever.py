"""Retriever Port - RAG 검색 추상화.

분리배출 규정 검색용.
"""

from abc import ABC, abstractmethod
from typing import Any


class RetrieverPort(ABC):
    """RAG 검색 포트.

    분리배출 규정 검색.
    """

    @abstractmethod
    def search(
        self,
        category: str,
        subcategory: str | None = None,
    ) -> dict[str, Any] | None:
        """분류 기반 검색."""
        pass

    @abstractmethod
    def search_by_keyword(
        self,
        keyword: str,
        limit: int = 3,
    ) -> list[dict[str, Any]]:
        """키워드 검색."""
        pass

    @abstractmethod
    def get_all_categories(self) -> list[str]:
        """카테고리 목록."""
        pass
