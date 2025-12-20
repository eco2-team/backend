"""SCAN 소스 리워드 평가 전략.

재활용 분리배출 스캔 결과를 기반으로 캐릭터를 매칭합니다.

평가 조건:
    1. source == SCAN
    2. major_category == "재활용폐기물"
    3. disposal_rules_present == True
    4. insufficiencies_present == False

매칭 로직:
    middle_category를 기준으로 캐릭터 필터링
    예: 플라스틱 → 플라봇, 유리 → 유리봇
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Sequence

from domains.character.core.constants import (
    MATCH_REASON_UNDEFINED,
    RECYCLABLE_WASTE_CATEGORY,
    REWARD_SOURCE_SCAN,
)
from domains.character.schemas.reward import CharacterRewardSource
from domains.character.services.evaluators.base import RewardEvaluator

if TYPE_CHECKING:
    from domains.character.models import Character
    from domains.character.schemas.reward import CharacterRewardRequest


class ScanRewardEvaluator(RewardEvaluator):
    """재활용 스캔 기반 리워드 평가.

    Attributes:
        RECYCLABLE_CATEGORY: 재활용폐기물 카테고리 상수
    """

    RECYCLABLE_CATEGORY = RECYCLABLE_WASTE_CATEGORY

    @property
    def source_label(self) -> str:
        """SCAN 리워드 소스 식별자."""
        return REWARD_SOURCE_SCAN

    def should_evaluate(self, payload: "CharacterRewardRequest") -> bool:
        """스캔 리워드 평가 조건 확인.

        조건:
            - source가 SCAN
            - 재활용폐기물 분류
            - 분리배출 규칙 존재
            - 부족한 정보 없음
        """
        classification = payload.classification
        return (
            payload.source == CharacterRewardSource.SCAN
            and classification.major_category.strip() == self.RECYCLABLE_CATEGORY
            and payload.disposal_rules_present
            and not payload.insufficiencies_present
        )

    def match_characters(
        self,
        payload: "CharacterRewardRequest",
        characters: Sequence["Character"],
    ) -> list["Character"]:
        """주어진 캐릭터 목록에서 match_label 기반 필터링."""
        match_label = self._resolve_match_label(payload)
        if not match_label:
            return []

        return [c for c in characters if c.match_label == match_label]

    def build_match_reason(self, payload: "CharacterRewardRequest") -> str:
        """분류 결과로부터 매칭 사유 생성.

        Format: "{middle}>{minor}" or "{middle}" or "{major}"
        """
        classification = payload.classification
        middle = (classification.middle_category or "").strip()
        minor = (classification.minor_category or "").strip()

        if middle and minor:
            return f"{middle}>{minor}"
        if middle:
            return middle

        major = (classification.major_category or "").strip()
        if major:
            return major

        return MATCH_REASON_UNDEFINED

    def _resolve_match_label(self, payload: "CharacterRewardRequest") -> str | None:
        """캐릭터 매칭에 사용할 label 결정.

        재활용폐기물: middle_category 사용
        그 외: middle → major 순으로 fallback
        """
        classification = payload.classification
        major = (classification.major_category or "").strip()
        middle = (classification.middle_category or "").strip()

        if major == self.RECYCLABLE_CATEGORY:
            return middle or None

        return middle or major or None
