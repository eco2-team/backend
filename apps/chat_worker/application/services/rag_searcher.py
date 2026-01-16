"""RAG Searcher Service.

분리수거 규정 검색 비즈니스 로직.
Port 의존 없음 - 검색 전략만 담당.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class RAGSearchResult:
    """RAG 검색 결과."""

    found: bool
    data: dict[str, Any] | None = None
    search_method: str = "none"  # "classification" | "keyword" | "none"
    matched_keyword: str | None = None


class RAGSearcherService:
    """RAG 검색 서비스 (순수 비즈니스 로직).

    검색 전략:
    1. 분류 기반 검색 (Vision 결과가 있는 경우)
    2. 키워드 기반 Fallback 검색

    Port 의존 없음 - Retriever는 Command에서 주입.
    """

    # 폐기물 키워드 목록 (검색 Fallback용)
    WASTE_KEYWORDS = frozenset(
        [
            "페트병",
            "플라스틱",
            "유리병",
            "캔",
            "종이",
            "비닐",
            "스티로폼",
            "음식물",
            "건전지",
            "형광등",
            "가전",
            "의류",
            "우유팩",
            "택배상자",
            "영수증",
            "휴지",
            "마스크",
        ]
    )

    def extract_keywords(self, message: str) -> list[str]:
        """메시지에서 폐기물 키워드 추출.

        Args:
            message: 사용자 메시지

        Returns:
            추출된 키워드 목록 (순서: 발견 순)
        """
        message_lower = message.lower()
        found = []
        for keyword in self.WASTE_KEYWORDS:
            if keyword in message_lower:
                found.append(keyword)
        return found

    def get_search_params_from_classification(
        self,
        classification: dict[str, Any] | None,
    ) -> tuple[str, str] | None:
        """분류 결과에서 검색 파라미터 추출.

        Args:
            classification: Vision 분류 결과

        Returns:
            (category, subcategory) 또는 None
        """
        if not classification:
            return None

        category = classification.get("classification", {}).get("major_category", "")
        subcategory = classification.get("classification", {}).get("minor_category", "")

        if category:
            return (category, subcategory)
        return None

    def determine_search_strategy(
        self,
        classification: dict[str, Any] | None,
        message: str,
    ) -> tuple[str, dict[str, Any]]:
        """검색 전략 결정.

        Args:
            classification: Vision 분류 결과
            message: 사용자 메시지

        Returns:
            (전략명, 전략 파라미터)
            - ("classification", {"category": ..., "subcategory": ...})
            - ("keyword", {"keywords": [...]})
            - ("none", {})
        """
        # 1. 분류 기반 검색 우선
        params = self.get_search_params_from_classification(classification)
        if params:
            return ("classification", {"category": params[0], "subcategory": params[1]})

        # 2. 키워드 기반 Fallback
        keywords = self.extract_keywords(message)
        if keywords:
            return ("keyword", {"keywords": keywords})

        # 3. 검색 불가
        return ("none", {})
