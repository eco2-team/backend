"""User gateway ports (interfaces)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol
from uuid import UUID

if TYPE_CHECKING:
    from apps.users.domain.entities.user import User


class UserQueryGateway(Protocol):
    """사용자 조회 포트."""

    async def get_by_id(self, user_id: UUID) -> User | None:
        """사용자 ID(UUID)로 조회합니다.

        Note: 통합 스키마에서 users.users.id는 UUID입니다.
        """
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
