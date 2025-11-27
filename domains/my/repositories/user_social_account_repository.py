from __future__ import annotations

from typing import Sequence
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from domains.my.models import AuthUserSocialAccount


class UserSocialAccountRepository:
    """Read-only access to social account information stored in the auth schema."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_by_user_id(self, user_id: UUID) -> Sequence[AuthUserSocialAccount]:
        stmt: Select[AuthUserSocialAccount] = (
            select(AuthUserSocialAccount)
            .where(AuthUserSocialAccount.user_id == user_id)
            .order_by(
                AuthUserSocialAccount.last_login_at.desc().nullslast(),
                AuthUserSocialAccount.provider.asc(),
            )
        )
        result = await self.session.scalars(stmt)
        return result.all()

    async def count_by_provider(self) -> dict[str, int]:
        stmt = (
            select(AuthUserSocialAccount.provider, func.count(AuthUserSocialAccount.id))
            .group_by(AuthUserSocialAccount.provider)
            .order_by(AuthUserSocialAccount.provider)
        )
        result = await self.session.execute(stmt)
        provider_counts = {provider: count for provider, count in result.all()}
        return provider_counts
