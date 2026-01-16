"""Local Asset Retriever - RetrieverPort 구현체.

폐기물 분류 규정 JSON 검색.
scan_worker/infrastructure/retrievers와 동일한 역할.

Port: application/ports/retrieval/retriever.py
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from chat_worker.application.ports.retrieval import RetrieverPort

logger = logging.getLogger(__name__)


class LocalAssetRetriever(RetrieverPort):
    """로컬 JSON 파일 기반 Retriever.

    assets/data/source/ 디렉토리의 JSON 파일들을 로드하여 검색.
    """

    def __init__(self, assets_path: str | Path | None = None):
        """초기화.

        Args:
            assets_path: 에셋 경로 (기본: infrastructure/assets/data/source)
        """
        if assets_path is None:
            self._assets_path = Path(__file__).parent.parent / "assets" / "data" / "source"
        else:
            self._assets_path = Path(assets_path)

        self._data: dict[str, dict] = {}
        self._categories: list[str] = []
        self._load_data()

        logger.info(
            "LocalAssetRetriever initialized",
            extra={
                "path": str(self._assets_path),
                "categories_count": len(self._categories),
            },
        )

    def _load_data(self) -> None:
        """JSON 파일들을 메모리에 로드."""
        if not self._assets_path.exists():
            logger.warning(
                "Assets path not found",
                extra={"path": str(self._assets_path)},
            )
            return

        for json_file in self._assets_path.glob("*.json"):
            try:
                with open(json_file, encoding="utf-8") as f:
                    data = json.load(f)
                category = json_file.stem
                self._data[category] = data
                self._categories.append(category)
                logger.debug("Loaded asset file", extra={"file": json_file.name})
            except Exception as e:
                logger.error(
                    "Failed to load asset file",
                    extra={"file": str(json_file), "error": str(e)},
                )

    def search(
        self,
        category: str,
        subcategory: str | None = None,
    ) -> dict[str, Any] | None:
        """분류 기반 검색.

        Args:
            category: 주요 카테고리 (예: "재활용", "일반")
            subcategory: 하위 카테고리 (선택)

        Returns:
            검색 결과 또는 None
        """
        # 직접 매칭
        for key, data in self._data.items():
            if category in key or key in category:
                return {
                    "key": key,
                    "category": category,
                    "subcategory": subcategory,
                    "data": data,
                }

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
        """키워드 검색.

        Args:
            keyword: 검색 키워드
            limit: 최대 결과 수

        Returns:
            검색 결과 리스트
        """
        results = []
        keyword_lower = keyword.lower()

        for key, data in self._data.items():
            # 파일명 매칭
            if keyword_lower in key.lower():
                results.append({"key": key, "data": data})
                continue

            # 내용 매칭
            data_str = json.dumps(data, ensure_ascii=False).lower()
            if keyword_lower in data_str:
                results.append({"key": key, "data": data})

        return results[:limit]

    def get_all_categories(self) -> list[str]:
        """전체 카테고리 목록.

        Returns:
            로드된 카테고리 리스트
        """
        return self._categories.copy()
