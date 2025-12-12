from __future__ import annotations

from typing import Sequence
from uuid import UUID

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from domains.character.database.session import get_db_session
from domains.character.models import Character
from domains.character.repositories import CharacterOwnershipRepository, CharacterRepository
from domains.character.schemas.catalog import CharacterAcquireResponse, CharacterProfile
from domains.character.schemas.reward import (
    CharacterRewardFailureReason,
    CharacterRewardRequest,
    CharacterRewardResponse,
    CharacterRewardSource,
    ClassificationSummary,
)

DEFAULT_CHARACTER_NAME = "이코"
DEFAULT_CHARACTER_SOURCE = "default-onboard"


class CharacterService:
    def __init__(self, session: AsyncSession = Depends(get_db_session)):
        self.session = session
        self.character_repo = CharacterRepository(session)
        self.ownership_repo = CharacterOwnershipRepository(session)

    async def catalog(self) -> list[CharacterProfile]:
        characters = await self.character_repo.list_all()
        if not characters:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="등록된 캐릭터가 없습니다.",
            )
        return [self._to_profile(character) for character in characters]

    async def grant_default_character(self, user_id: UUID) -> CharacterAcquireResponse:
        return await self._grant_character_by_name(
            user_id=user_id,
            character_name=DEFAULT_CHARACTER_NAME,
            source=DEFAULT_CHARACTER_SOURCE,
            allow_empty=True,
        )

    async def metrics(self) -> dict:
        return {
            "analyzed_users": 128,
            "catalog_size": 5,
            "history_entries": 56,
        }

    async def evaluate_reward(self, payload: CharacterRewardRequest) -> CharacterRewardResponse:
        classification = payload.classification
        reward_profile: CharacterProfile | None = None
        already_owned = False
        received = False
        match_reason: str | None = None

        should_evaluate = (
            payload.source == CharacterRewardSource.SCAN
            and classification.major_category.strip() == "재활용폐기물"
            and payload.disposal_rules_present
            and not payload.insufficiencies_present
        )

        if should_evaluate:
            match_reason = self._build_match_reason(classification)
            matches = await self._match_characters(classification)
            if matches:
                reward_profile, already_owned, failure_reason = await self._apply_reward(
                    payload.user_id, matches
                )
                received = (
                    failure_reason is None and reward_profile is not None and not already_owned
                )

        return self._to_reward_response(reward_profile, already_owned, received, match_reason)

    @staticmethod
    def _to_reward_response(
        profile: CharacterProfile | None,
        already_owned: bool,
        received: bool,
        match_reason: str | None,
    ) -> CharacterRewardResponse:
        reward_type = (profile.type or None) if profile else None
        return CharacterRewardResponse(
            received=received,
            already_owned=already_owned,
            name=profile.name if profile else None,
            dialog=profile.dialog if profile else None,
            match_reason=match_reason,
            character_type=reward_type,
            type=reward_type,
        )

    async def _grant_character_by_name(
        self,
        *,
        user_id: UUID,
        character_name: str,
        source: str,
        allow_empty: bool,
    ) -> CharacterAcquireResponse:
        normalized_name = character_name.strip()
        if not normalized_name:
            if allow_empty:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Default character name is not configured",
                )
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Character name required",
            )

        character = await self.character_repo.get_by_name(normalized_name)
        if character is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Character not found")

        existing = await self.ownership_repo.get_by_user_and_character(
            user_id=user_id,
            character_id=character.id,
        )
        if existing:
            return CharacterAcquireResponse(acquired=False, character=self._to_profile(character))

        await self.ownership_repo.upsert_owned(
            user_id=user_id,
            character=character,
            source=source,
        )
        await self.session.commit()
        return CharacterAcquireResponse(acquired=True, character=self._to_profile(character))

    async def _match_characters(self, classification: ClassificationSummary) -> list[Character]:
        match_label = self._resolve_match_label(classification)
        if not match_label:
            return []
        return await self.character_repo.list_by_match_label(match_label)

    @staticmethod
    def _resolve_match_label(classification: ClassificationSummary) -> str | None:
        major = (classification.major_category or "").strip()
        middle = (classification.middle_category or "").strip()
        if major == "재활용폐기물":
            return middle or None
        return middle or major or None

    @staticmethod
    def _build_match_reason(classification: ClassificationSummary) -> str:
        middle = (classification.middle_category or "").strip()
        minor = (classification.minor_category or "").strip()
        if middle and minor:
            return f"{middle}>{minor}"
        if middle:
            return middle
        major = (classification.major_category or "").strip()
        if major:
            return major
        return "미정의"

    async def _apply_reward(
        self,
        user_id: UUID,
        matches: Sequence[Character],
    ) -> tuple[CharacterProfile | None, bool, CharacterRewardFailureReason | None]:
        for match in matches:
            existing = await self.ownership_repo.get_by_user_and_character(
                user_id=user_id, character_id=match.id
            )
            if existing:
                return self._to_profile(match), True, None

            await self.ownership_repo.upsert_owned(
                user_id=user_id,
                character=match,
                source="scan-reward",
            )
            await self.session.commit()
            return self._to_profile(match), False, None

        return None, False, CharacterRewardFailureReason.CHARACTER_NOT_FOUND

    @staticmethod
    def _to_profile(character: Character) -> CharacterProfile:
        return CharacterProfile(
            name=character.name,
            type=str(character.type_label or "").strip(),
            dialog=str(character.dialog or character.description or "").strip(),
            match=str(character.match_label or "").strip() or None,
        )
