"""User character gateway ports (interfaces)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol
from uuid import UUID

if TYPE_CHECKING:
    from apps.users.domain.entities.user_character import UserCharacter


class UserCharacterQueryGateway(Protocol):
    """사용자 캐릭터 조회 포트."""

    async def list_by_user_id(self, user_id: UUID) -> list[UserCharacter]:
        """사용자의 캐릭터 목록을 조회합니다."""
        ...

    async def get_by_character_code(
        self, user_id: UUID, character_code: str
    ) -> UserCharacter | None:
        """특정 캐릭터의 소유 정보를 조회합니다."""
        ...

    async def count_by_user_id(self, user_id: UUID) -> int:
        """사용자의 캐릭터 수를 조회합니다."""
        ...
