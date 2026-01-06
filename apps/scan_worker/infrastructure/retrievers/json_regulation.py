"""JSON Regulation Retriever - RetrieverPort 구현체.

domains/_shared/waste_pipeline/rag.py 로직 이전.
JSON 파일 기반 Lite RAG.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from scan_worker.application.classify.ports.retriever import RetrieverPort

logger = logging.getLogger(__name__)


class JsonRegulationRetriever(RetrieverPort):
    """JSON 파일 기반 규정 검색 구현체.

    분류 결과에 맞는 JSON 파일을 찾아 배출 규정 반환.
    메모리 캐싱 적용.
    """

    def __init__(self, data_path: str | Path):
        """초기화.

        Args:
            data_path: 리소스 데이터 경로 (source/ 폴더 포함)
        """
        self._data_path = Path(data_path)
        self._source_dir = self._data_path / "source"
        self._cache: dict[str, dict[str, Any]] = {}
        logger.info(
            "JsonRegulationRetriever initialized (path=%s)",
            self._source_dir,
        )

    def get_disposal_rules(
        self,
        classification: dict[str, Any],
    ) -> dict[str, Any] | None:
        """분류 결과에 맞는 배출 규정 검색.

        Args:
            classification: Vision 분류 결과
                {
                    "classification": {
                        "major_category": "대분류",
                        "middle_category": "중분류",
                    },
                    ...
                }

        Returns:
            배출 규정 dict (매칭 실패 시 None)
        """
        # classification 추출
        cls = classification.get("classification", {})
        major_category = cls.get("major_category", "")
        middle_category = cls.get("middle_category", "")

        logger.debug(
            "Searching disposal rules (major=%s, middle=%s)",
            major_category,
            middle_category,
        )

        # 1) 재활용폐기물의 경우: {major_category}_{middle_category}.json
        if major_category == "재활용폐기물" and middle_category:
            filename = f"{major_category}_{middle_category}.json"
            result = self._load_json(filename)
            if result:
                return result

        # 2) 다른 카테고리의 경우: {major_category}.json
        if major_category:
            filename = f"{major_category}.json"
            result = self._load_json(filename)
            if result:
                return result

        # 3) 매칭 실패
        logger.warning(
            "No disposal rules found (major=%s, middle=%s)",
            major_category,
            middle_category,
        )
        return None

    def _load_json(self, filename: str) -> dict[str, Any] | None:
        """JSON 파일 로딩 (캐싱 적용).

        Args:
            filename: JSON 파일명

        Returns:
            JSON 내용 (없으면 None)
        """
        # 캐시 확인
        if filename in self._cache:
            logger.debug("Cache hit (filename=%s)", filename)
            return self._cache[filename]

        # 파일 로딩
        filepath = self._source_dir / filename
        if not filepath.exists():
            logger.debug("File not found (filepath=%s)", filepath)
            return None

        try:
            with filepath.open("r", encoding="utf-8") as f:
                data = json.load(f)
            self._cache[filename] = data
            logger.debug("File loaded (filepath=%s)", filepath)
            return data
        except json.JSONDecodeError as e:
            logger.error("JSON decode error (filepath=%s, error=%s)", filepath, e)
            return None
