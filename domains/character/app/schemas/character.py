from __future__ import annotations

from datetime import datetime
from typing import List
from uuid import UUID

from pydantic import BaseModel, Field


class CharacterAnalysisRequest(BaseModel):
    user_id: str
    preferences: List[str] = Field(default_factory=list)
    mood_score: float | None = None


class CharacterProfile(BaseModel):
    id: str
    name: str
    description: str
    compatibility_score: float
    traits: List[str]


class CharacterHistoryEntry(BaseModel):
    id: str
    character_id: str
    timestamp: datetime
    context: dict[str, str]


class CharacterAcquireRequest(BaseModel):
    user_id: UUID
    character_name: str = Field(min_length=1, max_length=120)


class CharacterSummary(BaseModel):
    id: UUID
    code: str
    name: str
    rarity: str
    description: str | None = None
    metadata: dict | None = None


class CharacterAcquireResponse(BaseModel):
    acquired: bool = Field(description="True when the character was newly unlocked")
    character: CharacterSummary
