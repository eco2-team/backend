from __future__ import annotations

from enum import Enum
from typing import Any, List
from uuid import UUID

from pydantic import BaseModel, Field


class CharacterRewardSource(str, Enum):
    SCAN = "scan"


class ClassificationSummary(BaseModel):
    major_category: str = Field(..., min_length=1)
    middle_category: str = Field(..., min_length=1)
    minor_category: str | None = None


class CharacterRewardFailureReason(str, Enum):
    """리워드 평가 실패 사유."""

    CHARACTER_NOT_FOUND = "character_not_seeded"


class CharacterRewardRequest(BaseModel):
    source: CharacterRewardSource = CharacterRewardSource.SCAN
    user_id: UUID
    task_id: str = Field(..., min_length=1)
    classification: ClassificationSummary
    situation_tags: List[str] = Field(default_factory=list)
    disposal_rules_present: bool = True
    insufficiencies_present: bool = True


class CharacterRewardResponse(BaseModel):
    """캐릭터 리워드 응답.

    Note:
        `type` 필드는 레거시 호환성을 위해 유지됩니다.
        신규 클라이언트는 `character_type` 사용을 권장합니다.
    """

    received: bool = Field(
        default=False,
        description="True when the character was newly granted as part of this reward evaluation",
    )
    already_owned: bool = Field(
        default=False, description="True when the user already possessed the character"
    )
    name: str | None = Field(default=None, description="Character name when available")
    dialog: str | None = Field(default=None, description="Character dialog to display")
    match_reason: str | None = Field(
        default=None, description="Why this character was selected for the reward"
    )
    character_type: str | None = Field(
        default=None, description="Primary type or trait of the rewarded character"
    )
    type: str | None = Field(
        default=None,
        description="[Deprecated] Use character_type instead. Kept for legacy client compatibility.",
        json_schema_extra={"deprecated": True},
    )

    def model_post_init(self, __context: Any) -> None:
        """type과 character_type 동기화 (레거시 호환성)."""
        if self.type is None and self.character_type is not None:
            self.type = self.character_type
        elif self.character_type is None and self.type is not None:
            self.character_type = self.type
