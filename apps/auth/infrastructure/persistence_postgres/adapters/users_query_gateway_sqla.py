"""SQLAlchemy Users Query Gateway.

UsersQueryGateway 포트의 구현체입니다.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select

from apps.auth.domain.entities.user import User
from apps.auth.domain.value_objects.user_id import UserId
from apps.auth.infrastructure.persistence_postgres.mappings.users import users_table
from apps.auth.infrastructure.persistence_postgres.mappings.users_social_account import (
    users_social_accounts_table,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class SqlaUsersQueryGateway:
    """SQLAlchemy 기반 Users Query Gateway.

    UsersQueryGateway 구현체.
    """

    def __init__(self, session: "AsyncSession") -> None:
        self._session = session

    async def get_by_id(self, user_id: UserId) -> User | None:
        """ID로 사용자 조회."""
        stmt = select(User).where(users_table.c.id == user_id.value)
        result = await self._session.execute(stmt)
        user = result.scalar_one_or_none()

        if user:
            # UserId Value Object로 변환
            user.id_ = UserId(value=user._id)
            # social_accounts는 별도 조회 필요 시 lazy load
            user.social_accounts = []

        return user

    async def get_by_provider(self, provider: str, provider_user_id: str) -> User | None:
        """OAuth 프로바이더 정보로 사용자 조회."""
        # 소셜 계정으로 조인하여 조회
        stmt = (
            select(User)
            .join(
                users_social_accounts_table,
                users_table.c.id == users_social_accounts_table.c.user_id,
            )
            .where(
                users_social_accounts_table.c.provider == provider,
                users_social_accounts_table.c.provider_user_id == provider_user_id,
            )
        )
        result = await self._session.execute(stmt)
        user = result.scalar_one_or_none()

        if user:
            user.id_ = UserId(value=user._id)
            user.social_accounts = []

        return user
