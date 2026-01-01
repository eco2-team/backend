"""User gateway ports (interfaces)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol
from uuid import UUID

if TYPE_CHECKING:
    from apps.users.domain.entities.user import User


class UserQueryGateway(Protocol):
    """사용자 조회 포트."""

    async def get_by_auth_user_id(self, auth_user_id: UUID) -> User | None:
        """auth_user_id로 사용자를 조회합니다."""
        ...

    async def get_by_id(self, user_id: int) -> User | None:
        """사용자 ID로 조회합니다."""
        ...


class UserCommandGateway(Protocol):
    """사용자 수정 포트."""

    async def create(self, user: User) -> User:
        """새 사용자를 생성합니다."""
        ...

    async def update(self, user: User) -> User:
        """사용자 정보를 업데이트합니다."""
        ...

    async def delete(self, user_id: int) -> None:
        """사용자를 삭제합니다."""
        ...
