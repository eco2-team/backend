"""Profile gateway ports (interfaces).

사용자 프로필 CRUD 인터페이스입니다.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol
from uuid import UUID

if TYPE_CHECKING:
    from apps.users.domain.entities.user import User


class ProfileQueryGateway(Protocol):
    """프로필 조회 포트."""

    async def get_by_id(self, user_id: UUID) -> User | None:
        """사용자 ID(UUID)로 조회합니다.

        Note: users.users.id는 UUID입니다.
        """
        ...


class ProfileCommandGateway(Protocol):
    """프로필 수정 포트."""

    async def create(self, user: User) -> User:
        """새 프로필을 생성합니다."""
        ...

    async def update(self, user: User) -> User:
        """프로필 정보를 업데이트합니다."""
        ...

    async def delete(self, user_id: UUID) -> None:
        """프로필을 삭제합니다."""
        ...
