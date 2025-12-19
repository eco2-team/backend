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
        description="Alias of character_type for clients expecting a 'type' field",
    )

    def model_post_init(self, __context: Any) -> None:
        if self.type is None and self.character_type is not None:
            self.type = self.character_type
        if self.character_type is None and self.type is not None:
            self.character_type = self.type
