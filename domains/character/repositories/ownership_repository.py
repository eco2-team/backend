from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from domains.character.enums import CharacterOwnershipStatus
from domains.character.models import Character, CharacterOwnership


class CharacterOwnershipRepository:
    """Data access helper for tracking user character ownership."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def upsert_owned(
        self,
        *,
        user_id: UUID,
        character: Character,
        source: str | None = None,
    ) -> CharacterOwnership:
        ownership = await self._get_internal(user_id=user_id, character_id=character.id)
        if ownership:
            ownership.status = CharacterOwnershipStatus.OWNED
            if source:
                ownership.source = source
            ownership.updated_at = datetime.now(timezone.utc)
            # Relationship might be expired if loaded without join
            if ownership.character is None:
                ownership.character = character
        else:
            ownership = CharacterOwnership(
                user_id=user_id,
                character_id=character.id,
                source=source,
                status=CharacterOwnershipStatus.OWNED,
            )
            ownership.character = character
            self.session.add(ownership)

        await self.session.flush()
        return ownership

    async def list_by_user(self, user_id: UUID) -> list[CharacterOwnership]:
        stmt = (
            select(CharacterOwnership)
            .options(selectinload(CharacterOwnership.character))
            .where(
                CharacterOwnership.user_id == user_id,
                CharacterOwnership.status == CharacterOwnershipStatus.OWNED,
            )
            .order_by(CharacterOwnership.acquired_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_user_and_character(
        self, user_id: UUID, character_id: UUID
    ) -> CharacterOwnership | None:
        return await self._get_internal(user_id=user_id, character_id=character_id)

    async def _get_internal(self, user_id: UUID, character_id: UUID) -> CharacterOwnership | None:
        stmt = (
            select(CharacterOwnership)
            .options(selectinload(CharacterOwnership.character))
            .where(
                CharacterOwnership.user_id == user_id,
                CharacterOwnership.character_id == character_id,
            )
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()
