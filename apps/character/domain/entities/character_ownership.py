"""CharacterOwnership Entity.

사용자의 캐릭터 소유권 엔티티입니다.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from apps.character.domain.enums import CharacterOwnershipStatus


@dataclass
class CharacterOwnership:
    """캐릭터 소유권 엔티티.

    사용자가 보유한 캐릭터 정보입니다.

    Attributes:
        id: 소유권 레코드 ID
        user_id: 사용자 ID
        character_id: 캐릭터 ID
        character_code: 캐릭터 코드 (멱등성 키)
        source: 획득 소스 (예: "scan-reward")
        status: 소유 상태
        acquired_at: 획득 시각
        updated_at: 수정 시각
        character: 연관된 캐릭터 엔티티 (옵션)
    """

    id: UUID
    user_id: UUID
    character_id: UUID
    character_code: str
    status: CharacterOwnershipStatus
    source: str | None = None
    acquired_at: datetime | None = None
    updated_at: datetime | None = None
    character: "Character | None" = None

    def __hash__(self) -> int:
        return hash(self.id)


# Circular import 해결
from apps.character.domain.entities.character import Character  # noqa: E402
