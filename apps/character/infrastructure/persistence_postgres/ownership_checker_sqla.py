"""SQLAlchemy Ownership Checker Implementation."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.character.application.reward.ports import OwnershipChecker
from apps.character.infrastructure.persistence_postgres.models import (
    CharacterOwnershipModel,
)


class SqlaOwnershipChecker(OwnershipChecker):
    """SQLAlchemy 기반 소유권 확인기."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize.

        Args:
            session: SQLAlchemy 비동기 세션
        """
        self._session = session

    async def is_owned(self, user_id: UUID, character_id: UUID) -> bool:
        """사용자가 캐릭터를 소유하고 있는지 확인합니다."""
        stmt = select(CharacterOwnershipModel.id).where(
            CharacterOwnershipModel.user_id == user_id,
            CharacterOwnershipModel.character_id == character_id,
            CharacterOwnershipModel.status == "owned",
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none() is not None
