"""SQLAlchemy implementation of user gateways."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.users.domain.entities.user import User

if TYPE_CHECKING:
    pass


class SqlaUserQueryGateway:
    """사용자 조회 게이트웨이 SQLAlchemy 구현."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_auth_user_id(self, auth_user_id: UUID) -> User | None:
        """auth_user_id로 사용자를 조회합니다."""
        result = await self._session.execute(
            select(User).where(User.auth_user_id == auth_user_id)
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, user_id: int) -> User | None:
        """사용자 ID로 조회합니다."""
        result = await self._session.execute(
            select(User).where(User.id == user_id)
        )
        return result.scalar_one_or_none()


class SqlaUserCommandGateway:
    """사용자 수정 게이트웨이 SQLAlchemy 구현."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, user: User) -> User:
        """새 사용자를 생성합니다."""
        self._session.add(user)
        await self._session.flush()
        return user

    async def update(self, user: User) -> User:
        """사용자 정보를 업데이트합니다."""
        merged = await self._session.merge(user)
        await self._session.flush()
        return merged

    async def delete(self, user_id: int) -> None:
        """사용자를 삭제합니다."""
        result = await self._session.execute(
            select(User).where(User.id == user_id)
        )
        user = result.scalar_one_or_none()
        if user:
            await self._session.delete(user)
            await self._session.flush()
