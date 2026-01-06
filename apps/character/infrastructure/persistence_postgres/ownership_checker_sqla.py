"""SQLAlchemy Ownership Checker Implementation.

Imperative Mapping을 사용하므로 도메인 엔티티를 직접 조회합니다.
"""

from uuid import UUID

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from character.application.reward.ports import OwnershipChecker
from character.domain.entities import CharacterOwnership


class SqlaOwnershipChecker(OwnershipChecker):
    """SQLAlchemy 기반 소유권 확인기.

    OwnershipChecker 포트를 구현합니다.
    """

    def __init__(self, session: AsyncSession) -> None:
        """Initialize.

        Args:
            session: SQLAlchemy 비동기 세션
        """
        self._session = session

    async def has_character(self, user_id: UUID, character_code: str) -> bool:
        """사용자가 해당 캐릭터를 보유하고 있는지 확인합니다."""
        stmt = select(
            exists().where(
                CharacterOwnership.user_id == user_id,
                CharacterOwnership.character_code == character_code,
            )
        )
        result = await self._session.execute(stmt)
        return bool(result.scalar())
