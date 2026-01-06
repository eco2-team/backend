"""SQLAlchemy Character Reader Implementation.

Imperative Mapping을 사용하므로 도메인 엔티티를 직접 조회합니다.
"""

from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from character.application.catalog.ports import CatalogReader
from character.application.reward.ports import CharacterMatcher
from character.domain.entities import Character

DEFAULT_CHARACTER_CODE = "char-eco"


class SqlaCharacterReader(CatalogReader, CharacterMatcher):
    """SQLAlchemy 기반 캐릭터 Reader.

    CatalogReader와 CharacterMatcher 포트를 구현합니다.
    """

    def __init__(self, session: AsyncSession) -> None:
        """Initialize.

        Args:
            session: SQLAlchemy 비동기 세션
        """
        self._session = session

    async def list_all(self) -> Sequence[Character]:
        """모든 캐릭터 목록을 조회합니다."""
        stmt = select(Character).order_by(Character.name)
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def match_by_label(self, match_label: str) -> Character | None:
        """매칭 라벨로 캐릭터를 찾습니다."""
        stmt = select(Character).where(Character.match_label == match_label)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_default(self) -> Character:
        """기본 캐릭터를 반환합니다."""
        stmt = select(Character).where(Character.code == DEFAULT_CHARACTER_CODE)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()

        if model is None:
            # 기본 캐릭터가 없으면 첫 번째 캐릭터 반환
            stmt = select(Character).limit(1)
            result = await self._session.execute(stmt)
            model = result.scalar_one()

        return model
