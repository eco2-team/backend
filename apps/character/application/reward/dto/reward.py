"""Reward DTOs."""

from dataclasses import dataclass
from uuid import UUID

from apps.character.domain.enums import CharacterRewardSource


@dataclass(frozen=True, slots=True)
class ClassificationSummary:
    """분류 결과 요약.

    Attributes:
        major_category: 대분류
        middle_category: 중분류
        minor_category: 소분류
        confidence: 신뢰도
    """

    major_category: str
    middle_category: str
    minor_category: str | None = None
    confidence: float | None = None


@dataclass(frozen=True, slots=True)
class RewardRequest:
    """리워드 평가 요청.

    Attributes:
        user_id: 사용자 ID
        source: 리워드 소스
        classification: 분류 결과 요약
        disposal_rules_present: 분리수거 규칙 존재 여부
        insufficiencies_present: 부적절 항목 존재 여부
    """

    user_id: UUID
    source: CharacterRewardSource
    classification: ClassificationSummary
    disposal_rules_present: bool = True
    insufficiencies_present: bool = False


@dataclass(frozen=True, slots=True)
class RewardResult:
    """리워드 평가 결과.

    Attributes:
        received: 리워드 수신 여부
        already_owned: 이미 소유 여부
        character_code: 매칭된 캐릭터 코드
        character_name: 캐릭터 이름
        character_type: 캐릭터 타입
        dialog: 캐릭터 대사
        match_reason: 매칭 이유
    """

    received: bool
    already_owned: bool
    character_code: str | None = None
    character_name: str | None = None
    character_type: str | None = None
    dialog: str | None = None
    match_reason: str | None = None
