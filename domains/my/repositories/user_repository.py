from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from domains.my.models import User


class UserRepository:
    """Data access helpers for My service entities."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_user(self, user_id: int) -> User | None:
        result = await self.session.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def get_by_auth_user_id(self, auth_user_id: UUID) -> User | None:
        result = await self.session.execute(select(User).where(User.auth_user_id == auth_user_id))
        return result.scalar_one_or_none()

    async def update_user(self, user: User, payload: dict[str, Any]) -> User:
        for field, value in payload.items():
            setattr(user, field, value)
        await self.session.flush()
        await self.session.refresh(user)
        return user

    async def delete_user(self, user_id: int) -> None:
        await self.session.execute(delete(User).where(User.id == user_id))

    async def metrics(self) -> dict[str, Any]:
        total = await self.session.scalar(select(func.count(User.id)))
        return {
            "total_users": int(total or 0),
        }
