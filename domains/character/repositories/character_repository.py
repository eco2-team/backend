from __future__ import annotations

from typing import Iterable
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from domains.character.models import Character


class CharacterRepository:
    """Data access helper for character definitions."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, character_id: UUID) -> Character | None:
        stmt = select(Character).where(Character.id == character_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_code(self, code: str) -> Character | None:
        stmt = select(Character).where(Character.code == code)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_all(self) -> list[Character]:
        result = await self.session.execute(select(Character))
        return list(result.scalars().all())

    async def get_by_name(self, name: str) -> Character | None:
        stmt = select(Character).where(func.lower(Character.name) == func.lower(name))
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_match_label(self, match_label: str) -> list[Character]:
        normalized = (match_label or "").strip()
        if not normalized:
            return []
        stmt = select(Character).where(func.lower(Character.match_label) == func.lower(normalized))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def add_many(self, characters: Iterable[Character]) -> None:
        self.session.add_all(list(characters))
