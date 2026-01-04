"""SQLAlchemy Character Reader Implementation."""

from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.character.application.catalog.ports import CatalogReader
from apps.character.application.reward.ports import CharacterMatcher
from apps.character.domain.entities import Character
from apps.character.infrastructure.persistence_postgres.mappers import (
    character_model_to_entity,
)
from apps.character.infrastructure.persistence_postgres.models import CharacterModel

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
        stmt = select(CharacterModel).order_by(CharacterModel.name)
        result = await self._session.execute(stmt)
        models = result.scalars().all()
        return [character_model_to_entity(m) for m in models]

    async def match_by_label(self, match_label: str) -> Character | None:
        """매칭 라벨로 캐릭터를 찾습니다."""
        stmt = select(CharacterModel).where(CharacterModel.match_label == match_label)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return character_model_to_entity(model) if model else None

    async def get_default(self) -> Character:
        """기본 캐릭터를 반환합니다."""
        stmt = select(CharacterModel).where(CharacterModel.code == DEFAULT_CHARACTER_CODE)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()

        if model is None:
            # 기본 캐릭터가 없으면 첫 번째 캐릭터 반환
            stmt = select(CharacterModel).limit(1)
            result = await self._session.execute(stmt)
            model = result.scalar_one()

        return character_model_to_entity(model)
