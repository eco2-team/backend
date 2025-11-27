from __future__ import annotations

from enum import Enum
from typing import List
from uuid import UUID

from pydantic import BaseModel, Field

from domains.character.schemas.character import CharacterSummary


class CharacterRewardSource(str, Enum):
    SCAN = "scan"


class ClassificationSummary(BaseModel):
    major_category: str = Field(..., min_length=1)
    middle_category: str = Field(..., min_length=1)
    minor_category: str | None = None


class CharacterRewardCandidate(BaseModel):
    name: str
    match_reason: str


class CharacterRewardFailureReason(str, Enum):
    UNSUPPORTED_SOURCE = "unsupported_source"
    UNSUPPORTED_CATEGORY = "unsupported_category"
    MISSING_RULES = "missing_disposal_rules"
    INSUFFICIENT_EVIDENCE = "insufficiencies_present"
    NO_MATCH = "no_matching_character"
    CHARACTER_NOT_FOUND = "character_not_seeded"


class CharacterRewardRequest(BaseModel):
    source: CharacterRewardSource = CharacterRewardSource.SCAN
    user_id: UUID
    task_id: str = Field(..., min_length=1)
    classification: ClassificationSummary
    situation_tags: List[str] = Field(default_factory=list)
    disposal_rules_present: bool = True
    insufficiencies_present: bool = True


class CharacterRewardResult(BaseModel):
    rewarded: bool
    already_owned: bool = False
    character: CharacterSummary | None = None
    reason: CharacterRewardFailureReason | None = None


class CharacterRewardResponse(BaseModel):
    candidates: List[CharacterRewardCandidate] = Field(default_factory=list)
    result: CharacterRewardResult
