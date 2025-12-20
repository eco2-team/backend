from __future__ import annotations

from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class CharacterProfile(BaseModel):
    name: str
    type: str
    dialog: str
    match: Optional[str] = None


class DefaultCharacterGrantRequest(BaseModel):
    user_id: UUID


class CharacterAcquireResponse(BaseModel):
    acquired: bool = Field(description="True when the character was newly unlocked")
    character: CharacterProfile


class GrantCharacterRequest(BaseModel):
    """gRPC 캐릭터 지급 요청 DTO.

    my_client.grant_character()에서 사용됩니다.
    """

    user_id: UUID
    character_id: UUID
    character_code: str
    character_name: str
    character_type: str | None = None
    character_dialog: str | None = None
    source: str = Field(..., description="리워드 소스 (예: 'scan-reward')")
