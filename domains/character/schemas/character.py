from __future__ import annotations

from typing import List
from uuid import UUID

from pydantic import BaseModel, Field


class CharacterProfile(BaseModel):
    id: str
    name: str
    description: str
    compatibility_score: float
    traits: List[str]


class CharacterAcquireRequest(BaseModel):
    user_id: UUID
    character_name: str = Field(min_length=1, max_length=120)


class DefaultCharacterGrantRequest(BaseModel):
    user_id: UUID


class CharacterSummary(BaseModel):
    name: str
    description: str | None = None


class CharacterAcquireResponse(BaseModel):
    acquired: bool = Field(description="True when the character was newly unlocked")
    character: CharacterSummary
