"""Retriever Port - RAG 검색 추상화.

분리배출 규정 검색용.

Retrieval 방식:
1. 분류 기반 검색 (category/subcategory)
2. 키워드 기반 검색
3. 태그 기반 컨텍스트 검색 (Anthropic Contextual Retrieval 스타일)
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class RetrievalContext:
    """태그 기반 검색 컨텍스트.

    Anthropic Contextual Retrieval 패턴:
    - 품목 태그: item_class_list.yaml에서 매칭된 품목
    - 상황 태그: situation_tags.yaml에서 매칭된 상황
    """

    matched_items: list[str] = field(default_factory=list)
    matched_situations: list[str] = field(default_factory=list)
    suggested_category: str | None = None


@dataclass
class ContextualSearchResult:
    """컨텍스트 기반 검색 결과.

    Phase 1 Citation과 연동:
    - chunk_id: 규정 파일 키
    - quoted_text: 관련 텍스트 인용
    - relevance: 관련성 수준
    """

    chunk_id: str
    category: str
    data: dict[str, Any]
    quoted_text: str = ""
    relevance: str = "medium"  # high | medium | low
    matched_tags: list[str] = field(default_factory=list)


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

    def extract_context(self, message: str) -> RetrievalContext:
        """메시지에서 컨텍스트 추출 (태그 매칭).

        Args:
            message: 사용자 메시지

        Returns:
            추출된 컨텍스트 (품목, 상황 태그)

        Note:
            기본 구현은 빈 컨텍스트 반환.
            TagBasedRetriever에서 오버라이드.
        """
        return RetrievalContext()

    def search_with_context(
        self,
        message: str,
        context: RetrievalContext | None = None,
    ) -> list[ContextualSearchResult]:
        """컨텍스트 기반 검색 (태그 매칭).

        Args:
            message: 사용자 메시지
            context: 추출된 컨텍스트 (없으면 자동 추출)

        Returns:
            컨텍스트 기반 검색 결과 목록

        Note:
            기본 구현은 빈 리스트 반환.
            TagBasedRetriever에서 오버라이드.
        """
        return []
