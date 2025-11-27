from __future__ import annotations

from uuid import UUID

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from domains.character.database.session import get_db_session as get_character_db_session
from domains.character.models.character import CharacterOwnership
from domains.character.repositories import CharacterOwnershipRepository
from domains.my.schemas import UserCharacter


class UserCharacterService:
    def __init__(self, session: AsyncSession = Depends(get_character_db_session)):
        self.session = session
        self.repo = CharacterOwnershipRepository(session)

    async def list_owned(self, user_id: UUID) -> list[UserCharacter]:
        ownerships = await self.repo.list_by_user(user_id)
        return [self._to_schema(entry) for entry in ownerships]

    @staticmethod
    def _to_schema(entry: CharacterOwnership) -> UserCharacter:
        character = entry.character
        return UserCharacter(
            id=character.id,
            code=character.code,
            name=character.name,
            rarity=character.rarity,
            description=character.description,
            metadata=character.metadata,
            acquired_at=entry.acquired_at,
        )
