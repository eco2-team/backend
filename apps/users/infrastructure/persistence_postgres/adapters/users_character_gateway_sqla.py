"""SQLAlchemy implementation of users character gateway."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.users.domain.entities.user_character import UserCharacter


class SqlaUsersCharacterQueryGateway:
    """사용자 캐릭터 조회 게이트웨이 SQLAlchemy 구현."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_by_user_id(self, user_id: UUID) -> list[UserCharacter]:
        """사용자의 캐릭터 목록을 조회합니다."""
        result = await self._session.execute(
            select(UserCharacter)
            .where(UserCharacter.user_id == user_id)
            .order_by(UserCharacter.acquired_at.desc())
        )
        return list(result.scalars().all())

    async def get_by_character_code(
        self, user_id: UUID, character_code: str
    ) -> UserCharacter | None:
        """특정 캐릭터의 소유 정보를 조회합니다."""
        result = await self._session.execute(
            select(UserCharacter).where(
                UserCharacter.user_id == user_id,
                UserCharacter.character_code == character_code,
            )
        )
        return result.scalar_one_or_none()

    async def count_by_user_id(self, user_id: UUID) -> int:
        """사용자의 캐릭터 수를 조회합니다."""
        result = await self._session.execute(
            select(func.count()).select_from(UserCharacter).where(UserCharacter.user_id == user_id)
        )
        return result.scalar() or 0
