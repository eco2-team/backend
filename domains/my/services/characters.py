from __future__ import annotations

from uuid import UUID

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from domains.character.database.session import get_db_session as get_character_db_session
from domains.character.models.character import CharacterOwnership
from domains.character.repositories import CharacterOwnershipRepository, CharacterRepository
from domains.my.schemas import UserCharacter


class UserCharacterService:
    def __init__(self, session: AsyncSession = Depends(get_character_db_session)):
        self.session = session
        self.repo = CharacterOwnershipRepository(session)
        self.character_repo = CharacterRepository(session)

    async def list_owned(self, user_id: UUID) -> list[UserCharacter]:
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

    @staticmethod
    def _to_schema(entry: CharacterOwnership) -> UserCharacter:
        character = entry.character
        metadata = getattr(character, "metadata_json", None) or {}
        type_value = metadata.get("type") or metadata.get("typeLabel") or ""
        dialog_value = metadata.get("dialog") or metadata.get("dialogue") or ""
        return UserCharacter(
            id=character.id,
            code=character.code,
            name=character.name,
            type=str(type_value),
            dialog=str(dialog_value),
            acquired_at=entry.acquired_at,
        )
