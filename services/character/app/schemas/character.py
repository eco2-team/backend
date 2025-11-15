from datetime import datetime
from typing import List

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
