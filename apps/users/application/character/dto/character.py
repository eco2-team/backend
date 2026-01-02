"""User character DTOs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True, slots=True)
class UserCharacterDTO:
    """사용자 캐릭터 DTO."""

    id: UUID
    character_id: UUID
    character_code: str
    character_name: str
    character_type: str | None
    character_dialog: str | None
    source: str | None
    status: str
    acquired_at: datetime


@dataclass(frozen=True, slots=True)
class CharacterOwnership:
    """캐릭터 소유 여부 DTO (domains/my 호환)."""

    character_name: str
    owned: bool
