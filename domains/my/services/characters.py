from __future__ import annotations

from uuid import UUID

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from domains.character.database.session import get_db_session as get_character_db_session
from domains.character.models.character import CharacterOwnership
from domains.character.repositories import CharacterOwnershipRepository, CharacterRepository
from domains.character.services.character import (
    DEFAULT_CHARACTER_NAME,
    DEFAULT_CHARACTER_SOURCE,
)
from domains.my.schemas import UserCharacter


class UserCharacterService:
    def __init__(self, session: AsyncSession = Depends(get_character_db_session)):
        self.session = session
        self.repo = CharacterOwnershipRepository(session)
        self.character_repo = CharacterRepository(session)

    async def list_owned(self, user_id: UUID) -> list[UserCharacter]:
        ownerships = await self.repo.list_by_user(user_id)
        if not ownerships:
            created = await self._ensure_default_character(user_id)
            if created:
                ownerships = await self.repo.list_by_user(user_id)
        return [self._to_schema(entry) for entry in ownerships]

    async def owns_character(self, user_id: UUID, character_name: str) -> bool:
        normalized_name = character_name.strip()
        if not normalized_name:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Character name is required",
            )

        character = await self.character_repo.get_by_name(normalized_name)
        if character is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Character not found")

        ownership = await self.repo.get_by_user_and_character(
            user_id=user_id,
            character_id=character.id,
        )
        return ownership is not None

    async def _ensure_default_character(self, user_id: UUID) -> bool:
        character = await self.character_repo.get_by_name(DEFAULT_CHARACTER_NAME)
        if character is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Default character is not configured",
            )

        existing = await self.repo.get_by_user_and_character(
            user_id=user_id, character_id=character.id
        )
        if existing:
            return False

        await self.repo.upsert_owned(
            user_id=user_id,
            character=character,
            source=DEFAULT_CHARACTER_SOURCE,
        )
        await self.session.commit()
        return True

    @staticmethod
    def _to_schema(entry: CharacterOwnership) -> UserCharacter:
        character = entry.character
        type_value = str(character.type_label or "").strip()
        dialog_value = str(character.dialog or "").strip()
        return UserCharacter(
            id=character.id,
            code=character.code,
            name=character.name,
            type=type_value,
            dialog=dialog_value,
            acquired_at=entry.acquired_at,
        )
