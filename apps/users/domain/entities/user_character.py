"""UserCharacter entity - Core domain object for character ownership."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4

from apps.users.domain.enums.user_character_status import UserCharacterStatus


@dataclass
class UserCharacter:
    """사용자 캐릭터 소유 엔티티.

    users.user_characters 테이블에 매핑됩니다.
    character 도메인과 FK 없이 독립성을 유지합니다.
    """

    id: UUID = field(default_factory=uuid4)
    user_id: UUID | None = None
    character_id: UUID | None = None
    character_code: str = ""
    character_name: str = ""
    character_type: str | None = None
    character_dialog: str | None = None
    source: str | None = None
    status: str = UserCharacterStatus.OWNED.value  # "owned"
    acquired_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def burn(self) -> None:
        """캐릭터를 소각 처리합니다."""
        self.status = UserCharacterStatus.BURNED.value
        self.updated_at = datetime.utcnow()

    def trade(self) -> None:
        """캐릭터를 거래 처리합니다."""
        self.status = UserCharacterStatus.TRADED.value
        self.updated_at = datetime.utcnow()
