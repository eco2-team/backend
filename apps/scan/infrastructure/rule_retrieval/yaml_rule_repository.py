"""YAML Rule Repository Adapter.

기존 domains/_shared/waste_pipeline/rag 모듈을 래핑하여 정합성 유지.
"""

from __future__ import annotations

import logging
from typing import Any

from apps.scan.application.pipeline.ports.rule_repository import RuleRepository

logger = logging.getLogger(__name__)


class YamlRuleRepository(RuleRepository):
    """YAML 기반 배출 규정 저장소 Adapter.

    기존 waste_pipeline의 RAG 모듈을 재사용합니다.
    """

    def get_disposal_rules(
        self,
        classification_result: dict[str, Any],
    ) -> dict[str, Any] | None:
        """분류 결과에 매칭되는 배출 규정 검색.

        기존 get_disposal_rules 함수를 사용하여 정합성 유지.
        """
        from domains._shared.waste_pipeline.rag import get_disposal_rules as _get_rules

        try:
            return _get_rules(classification_result)
        except Exception as e:
            logger.warning(
                "disposal_rules_search_failed",
                extra={"error": str(e)},
            )
            return None

    def get_all_categories(self) -> list[dict[str, Any]]:
        """모든 카테고리 목록 반환.

        기존 domains/scan에서 사용하는 카테고리 목록을 반환합니다.
        """
        # TODO: YAML 파일에서 동적 로드
        return [
            {
                "id": 1,
                "name": "recyclable",
                "display_name": "재활용폐기물",
                "instructions": [
                    "내용물을 비우고 헹굽니다",
                    "라벨을 제거합니다",
                    "재질별로 분리합니다",
                ],
            },
            {
                "id": 2,
                "name": "general",
                "display_name": "일반폐기물",
                "instructions": [
                    "종량제 봉투에 담습니다",
                    "음식물이 묻지 않도록 합니다",
                ],
            },
            {
                "id": 3,
                "name": "food",
                "display_name": "음식물폐기물",
                "instructions": [
                    "물기를 제거합니다",
                    "음식물 전용 봉투에 담습니다",
                ],
            },
            {
                "id": 4,
                "name": "bulky",
                "display_name": "대형폐기물",
                "instructions": [
                    "구청에 수거 신청합니다",
                    "스티커를 부착합니다",
                ],
            },
        ]
