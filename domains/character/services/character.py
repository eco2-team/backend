from __future__ import annotations

from typing import Sequence
from uuid import UUID

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from domains.character.database.session import get_db_session
from domains.character.models import Character
from domains.character.repositories import CharacterOwnershipRepository, CharacterRepository
from domains.character.schemas.character import (
    CharacterAcquireRequest,
    CharacterAcquireResponse,
    CharacterProfile,
    CharacterSummary,
)
from domains.character.schemas.reward import (
    CharacterRewardCandidate,
    CharacterRewardFailureReason,
    CharacterRewardRequest,
    CharacterRewardResponse,
    CharacterRewardResult,
    CharacterRewardSource,
    ClassificationSummary,
)

DISQUALIFYING_TAGS = {
    "내용물_있음",
    "라벨_부착",
    "뚜껑_있음",
    "오염됨",
    "미분류_소분류",
}
DEFAULT_CHARACTER_NAME = "이코"
DEFAULT_CHARACTER_SOURCE = "default-onboard"


class CharacterService:
    def __init__(self, session: AsyncSession = Depends(get_db_session)):
        self.session = session
        self.character_repo = CharacterRepository(session)
        self.ownership_repo = CharacterOwnershipRepository(session)

    async def catalog(self) -> list[CharacterProfile]:
        return [
            CharacterProfile(
                id="catalog-guardian",
                name="Guardian",
                description="Protects nature and educates neighbors.",
                compatibility_score=0.93,
                traits=["educator", "community-builder"],
            ),
            CharacterProfile(
                id="catalog-strategist",
                name="Strategist",
                description="Optimizes recycling routes and logistics.",
                compatibility_score=0.85,
                traits=["analyst", "planner"],
            ),
        ]

    async def acquire_character(self, payload: CharacterAcquireRequest) -> CharacterAcquireResponse:
        return await self._grant_character_by_name(
            user_id=payload.user_id,
            character_name=payload.character_name,
            source="api-acquire",
            allow_empty=False,
        )

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
        candidates: list[CharacterRewardCandidate] = []
        failure_reason: CharacterRewardFailureReason | None = None
        rewarded_summary: CharacterSummary | None = None
        already_owned = False

        classification = payload.classification

        if payload.source != CharacterRewardSource.SCAN:
            failure_reason = CharacterRewardFailureReason.UNSUPPORTED_SOURCE
        elif classification.major_category.strip() != "재활용폐기물":
            failure_reason = CharacterRewardFailureReason.UNSUPPORTED_CATEGORY
        elif not payload.disposal_rules_present:
            failure_reason = CharacterRewardFailureReason.MISSING_RULES
        elif self._has_disqualifying_tags(payload.situation_tags):
            failure_reason = CharacterRewardFailureReason.DISQUALIFYING_TAGS
        else:
            matches = await self._match_characters(classification)
            candidates = [
                CharacterRewardCandidate(
                    name=match.name,
                    match_reason=self._build_match_reason(classification),
                )
                for match in matches
            ]
            if not matches:
                failure_reason = CharacterRewardFailureReason.NO_MATCH
            else:
                (
                    rewarded_summary,
                    already_owned,
                    failure_reason,
                ) = await self._apply_reward(payload.user_id, matches)

        if failure_reason:
            result = CharacterRewardResult(
                rewarded=False,
                already_owned=already_owned,
                character=rewarded_summary,
                reason=failure_reason,
            )
        else:
            result = CharacterRewardResult(
                rewarded=not already_owned,
                already_owned=already_owned,
                character=rewarded_summary,
            )

        return CharacterRewardResponse(candidates=candidates, result=result)

    @staticmethod
    def _to_summary(character) -> CharacterSummary:
        return CharacterSummary(
            name=character.name,
            description=character.description,
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
            return CharacterAcquireResponse(acquired=False, character=self._to_summary(character))

        await self.ownership_repo.upsert_owned(
            user_id=user_id,
            character=character,
            source=source,
        )
        await self.session.commit()
        return CharacterAcquireResponse(acquired=True, character=self._to_summary(character))

    @staticmethod
    def _has_disqualifying_tags(tags: Sequence[str]) -> bool:
        normalized = {tag.strip() for tag in tags if isinstance(tag, str)}
        return any(tag in DISQUALIFYING_TAGS for tag in normalized)

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
    ) -> tuple[CharacterSummary | None, bool, CharacterRewardFailureReason | None]:
        for match in matches:
            existing = await self.ownership_repo.get_by_user_and_character(
                user_id=user_id, character_id=match.id
            )
            if existing:
                return self._to_summary(match), True, None

            await self.ownership_repo.upsert_owned(
                user_id=user_id,
                character=match,
                source="scan-reward",
            )
            await self.session.commit()
            return self._to_summary(match), False, None

        return None, False, CharacterRewardFailureReason.CHARACTER_NOT_FOUND
