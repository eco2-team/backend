"""Tag-Based Retriever - 태그 매칭 기반 컨텍스트 검색.

Anthropic Contextual Retrieval 패턴 적용:
- item_class_list.yaml: 품목 분류 (약 200개)
- situation_tags.yaml: 상황 태그 (약 100개)

참조: docs/foundations/27-rag-evaluation-strategy.md (3.3절 Contextual Retrieval)
"""

from __future__ import annotations

import json
import logging
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from chat_worker.application.ports.retrieval import (
    ContextualSearchResult,
    RetrievalContext,
    RetrieverPort,
)

logger = logging.getLogger(__name__)

# 에셋 경로
ASSETS_DIR = Path(__file__).parent.parent / "assets" / "data"


@lru_cache(maxsize=1)
def _load_item_class_list() -> dict[str, Any]:
    """품목 분류 YAML 로드 (캐싱)."""
    path = ASSETS_DIR / "item_class_list.yaml"
    if not path.exists():
        logger.warning(f"item_class_list.yaml not found: {path}")
        return {}
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


@lru_cache(maxsize=1)
def _load_situation_tags() -> list[str]:
    """상황 태그 YAML 로드 (캐싱)."""
    path = ASSETS_DIR / "situation_tags.yaml"
    if not path.exists():
        logger.warning(f"situation_tags.yaml not found: {path}")
        return []
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    # situation_tags 키 하위의 모든 태그 추출
    tags = data.get("situation_tags", [])
    if isinstance(tags, list):
        return [t for t in tags if isinstance(t, str)]
    return []


def _build_item_index() -> dict[str, tuple[str, str]]:
    """품목 → (대분류, 중분류) 인덱스 빌드.

    Returns:
        {품목명: (대분류, 중분류)} 딕셔너리
    """
    index = {}
    data = _load_item_class_list()
    item_classes = data.get("item_class_list", {})

    for major_category, sub_dict in item_classes.items():
        if isinstance(sub_dict, dict):
            for minor_category, items in sub_dict.items():
                if isinstance(items, list):
                    for item in items:
                        if isinstance(item, str):
                            index[item.lower()] = (major_category, minor_category)
        elif isinstance(sub_dict, list):
            # 일반종량제폐기물 같은 플랫 구조
            for item in sub_dict:
                if isinstance(item, str):
                    index[item.lower()] = (major_category, "")

    return index


class TagBasedRetriever(RetrieverPort):
    """태그 기반 컨텍스트 Retriever.

    LocalAssetRetriever를 확장하여 태그 매칭 기능 추가.

    검색 전략:
    1. 메시지에서 품목 태그 추출 (item_class_list)
    2. 메시지에서 상황 태그 추출 (situation_tags)
    3. 태그에 맞는 규정 섹션만 추출하여 Evidence 형식으로 반환
    """

    def __init__(self, assets_path: str | Path | None = None):
        """초기화.

        Args:
            assets_path: 에셋 경로 (기본: infrastructure/assets/data/source)
        """
        if assets_path is None:
            self._assets_path = ASSETS_DIR / "source"
        else:
            self._assets_path = Path(assets_path)

        self._data: dict[str, dict] = {}
        self._categories: list[str] = []
        self._item_index = _build_item_index()
        self._situation_tags = _load_situation_tags()
        self._load_data()

        logger.info(
            "TagBasedRetriever initialized",
            extra={
                "path": str(self._assets_path),
                "categories_count": len(self._categories),
                "item_count": len(self._item_index),
                "situation_tags_count": len(self._situation_tags),
            },
        )

    def _load_data(self) -> None:
        """JSON 파일들을 메모리에 로드."""
        if not self._assets_path.exists():
            logger.warning(f"Assets path not found: {self._assets_path}")
            return

        for json_file in self._assets_path.glob("*.json"):
            try:
                with open(json_file, encoding="utf-8") as f:
                    data = json.load(f)
                category = json_file.stem
                self._data[category] = data
                self._categories.append(category)
            except Exception as e:
                logger.error(f"Failed to load {json_file}: {e}")

    # ========== RetrieverPort 기본 구현 ==========

    def search(
        self,
        category: str,
        subcategory: str | None = None,
    ) -> dict[str, Any] | None:
        """분류 기반 검색."""
        for key, data in self._data.items():
            if category in key or key in category:
                return {"key": key, "category": category, "subcategory": subcategory, "data": data}

        # 약어 매핑
        category_map = {
            "재활용": "재활용폐기물",
            "일반": "일반종량제폐기물",
            "음식물": "음식물류폐기물",
            "대형": "대형폐기물",
            "유해": "생활계유해폐기물",
            "불연성": "불연성종량제폐기물",
            "공사장": "공사장생활폐기물",
        }

        for short, full in category_map.items():
            if short in category:
                for key, data in self._data.items():
                    if full in key:
                        return {
                            "key": key,
                            "category": category,
                            "subcategory": subcategory,
                            "data": data,
                        }
        return None

    def search_by_keyword(
        self,
        keyword: str,
        limit: int = 3,
    ) -> list[dict[str, Any]]:
        """키워드 검색."""
        results = []
        keyword_lower = keyword.lower()

        for key, data in self._data.items():
            if keyword_lower in key.lower():
                results.append({"key": key, "data": data})
                continue

            data_str = json.dumps(data, ensure_ascii=False).lower()
            if keyword_lower in data_str:
                results.append({"key": key, "data": data})

        return results[:limit]

    def get_all_categories(self) -> list[str]:
        """카테고리 목록."""
        return self._categories.copy()

    # ========== 태그 기반 컨텍스트 검색 ==========

    def extract_context(self, message: str) -> RetrievalContext:
        """메시지에서 컨텍스트 추출 (태그 매칭).

        Args:
            message: 사용자 메시지

        Returns:
            추출된 컨텍스트 (품목, 상황 태그)
        """
        message_lower = message.lower()
        message_normalized = self._normalize_message(message)

        # 1. 품목 태그 추출
        matched_items = []
        suggested_category = None

        for item, (major, minor) in self._item_index.items():
            if item in message_normalized:
                matched_items.append(item)
                if suggested_category is None:
                    suggested_category = major

        # 2. 상황 태그 추출
        matched_situations = []
        for tag in self._situation_tags:
            # 태그 정규화 (언더스코어 → 공백/없음)
            tag_variants = [
                tag.lower(),
                tag.lower().replace("_", " "),
                tag.lower().replace("_", ""),
            ]
            for variant in tag_variants:
                if variant in message_lower:
                    matched_situations.append(tag)
                    break

        logger.debug(
            "Context extracted",
            extra={
                "items": matched_items,
                "situations": matched_situations,
                "suggested_category": suggested_category,
            },
        )

        return RetrievalContext(
            matched_items=matched_items,
            matched_situations=matched_situations,
            suggested_category=suggested_category,
        )

    def search_with_context(
        self,
        message: str,
        context: RetrievalContext | None = None,
    ) -> list[ContextualSearchResult]:
        """컨텍스트 기반 검색 (태그 매칭).

        Anthropic Contextual Retrieval 패턴:
        - 품목/상황 태그에 맞는 규정만 추출
        - Evidence 형식 (chunk_id, quoted_text, relevance)

        Args:
            message: 사용자 메시지
            context: 추출된 컨텍스트 (없으면 자동 추출)

        Returns:
            컨텍스트 기반 검색 결과 목록
        """
        if context is None:
            context = self.extract_context(message)

        results: list[ContextualSearchResult] = []
        all_tags = context.matched_items + context.matched_situations

        if not all_tags:
            # 태그가 없으면 키워드 검색으로 폴백
            return self._fallback_keyword_search(message)

        # 태그에 매칭되는 규정 검색
        for key, data in self._data.items():
            matched_tags = []
            relevance = "low"
            quoted_text = ""

            # 카테고리 매칭
            if context.suggested_category and context.suggested_category in key:
                matched_tags.append(context.suggested_category)
                relevance = "high"

            # 규정 내용에서 태그 검색
            data_str = json.dumps(data, ensure_ascii=False).lower()

            for tag in all_tags:
                tag_lower = tag.lower()
                if tag_lower in data_str:
                    matched_tags.append(tag)
                    if relevance != "high":
                        relevance = "medium"

            if matched_tags:
                # 관련 텍스트 인용 추출
                quoted_text = self._extract_relevant_quote(data, all_tags)

                results.append(
                    ContextualSearchResult(
                        chunk_id=key,
                        category=data.get("category", key),
                        data=data,
                        quoted_text=quoted_text,
                        relevance=relevance,
                        matched_tags=matched_tags,
                    )
                )

        # 관련성 순 정렬
        relevance_order = {"high": 0, "medium": 1, "low": 2}
        results.sort(key=lambda x: relevance_order.get(x.relevance, 3))

        logger.info(
            "Contextual search completed",
            extra={
                "results_count": len(results),
                "tags_used": all_tags,
            },
        )

        return results

    def _normalize_message(self, message: str) -> str:
        """메시지 정규화 (품목 매칭용)."""
        # 소문자 변환
        normalized = message.lower()
        # 공백 정규화
        normalized = re.sub(r"\s+", "", normalized)
        return normalized

    def _extract_relevant_quote(self, data: dict, tags: list[str]) -> str:
        """규정에서 관련 텍스트 인용 추출.

        Args:
            data: 규정 데이터
            tags: 검색 태그

        Returns:
            관련 텍스트 (50자 이내)
        """
        # 우선순위: 배출방법_공통 → 배출불가_품목_안내 → 대상_설명
        priority_fields = ["배출방법_공통", "배출불가_품목_안내", "대상_설명", "아이콘_절차"]

        for field_name in priority_fields:
            field_data = data.get(field_name)

            if isinstance(field_data, list) and field_data:
                # 태그가 포함된 항목 우선
                for item in field_data:
                    if isinstance(item, str):
                        for tag in tags:
                            if tag.lower() in item.lower():
                                return item[:80] + ("..." if len(item) > 80 else "")
                # 없으면 첫 번째 항목
                return str(field_data[0])[:80]

            elif isinstance(field_data, dict):
                # 딕셔너리면 태그와 매칭되는 키 찾기
                for tag in tags:
                    for k, v in field_data.items():
                        if tag.lower() in k.lower():
                            return f"{k}: {v}"[:80]

        return ""

    def _fallback_keyword_search(self, message: str) -> list[ContextualSearchResult]:
        """키워드 기반 폴백 검색.

        Args:
            message: 사용자 메시지

        Returns:
            검색 결과 목록
        """
        # 기본 키워드 목록
        keywords = [
            "페트병", "플라스틱", "유리병", "캔", "종이", "비닐",
            "스티로폼", "음식물", "건전지", "형광등", "가전", "의류",
        ]

        results = []
        message_lower = message.lower()

        for keyword in keywords:
            if keyword in message_lower:
                keyword_results = self.search_by_keyword(keyword, limit=1)
                for r in keyword_results:
                    results.append(
                        ContextualSearchResult(
                            chunk_id=r.get("key", ""),
                            category=r.get("key", ""),
                            data=r.get("data", {}),
                            quoted_text="",
                            relevance="low",
                            matched_tags=[keyword],
                        )
                    )
                break

        return results
