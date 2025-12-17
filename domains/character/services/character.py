from __future__ import annotations

import logging
from typing import Sequence
from uuid import UUID

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from domains.character.database.session import get_db_session
from domains.character.models import Character
from domains.character.repositories import CharacterOwnershipRepository, CharacterRepository
from domains.character.rpc.my_client import get_my_client
from domains.character.schemas.catalog import CharacterAcquireResponse, CharacterProfile
from domains.character.schemas.reward import (
    CharacterRewardFailureReason,
    CharacterRewardRequest,
    CharacterRewardResponse,
    CharacterRewardSource,
    ClassificationSummary,
)
from domains.character.metrics import REWARD_EVALUATION_TOTAL, REWARD_GRANTED_TOTAL

logger = logging.getLogger(__name__)

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

    async def get_default_character(self) -> Character | None:
        """기본 캐릭터(이코) 정보 조회. my 도메인에서 사용."""
        return await self.character_repo.get_by_name(DEFAULT_CHARACTER_NAME)

    async def metrics(self) -> dict:
        return {
            "analyzed_users": 128,
            "catalog_size": 5,
            "history_entries": 56,
        }

    async def evaluate_reward(self, payload: CharacterRewardRequest) -> CharacterRewardResponse:
        logger.info(
            "Reward evaluation started",
            extra={"user_id": str(payload.user_id), "source": payload.source.value},
        )

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

                # Record metrics
                status_label = "success" if received else "failed"
                if already_owned:
                    status_label = "already_owned"
                elif failure_reason:
                    status_label = f"failed_{failure_reason.value}"

                REWARD_EVALUATION_TOTAL.labels(
                    status=status_label, source=payload.source.value
                ).inc()

                if received and reward_profile:
                    REWARD_GRANTED_TOTAL.labels(
                        character_name=reward_profile.name, type=reward_profile.type or "unknown"
                    ).inc()
            else:
                REWARD_EVALUATION_TOTAL.labels(status="no_match", source=payload.source.value).inc()
        else:
            REWARD_EVALUATION_TOTAL.labels(status="skipped", source=payload.source.value).inc()

        logger.info(
            "Reward evaluation completed",
            extra={
                "user_id": str(payload.user_id),
                "received": received,
                "already_owned": already_owned,
                "character_name": reward_profile.name if reward_profile else None,
            },
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

        # 1. character.character_ownerships에 저장 (기존 로직 유지)
        await self.ownership_repo.upsert_owned(
            user_id=user_id,
            character=character,
            source=source,
        )
        await self.session.commit()

        # 2. my 도메인에 gRPC로 동기화
        await self._sync_to_my_domain(
            user_id=user_id,
            character=character,
            source=source,
        )

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

            # 1. character.character_ownerships에 저장 (기존 로직 유지)
            await self.ownership_repo.upsert_owned(
                user_id=user_id,
                character=match,
                source="scan-reward",
            )
            await self.session.commit()

            # 2. my 도메인에 gRPC로 동기화
            await self._sync_to_my_domain(
                user_id=user_id,
                character=match,
                source="scan-reward",
            )

            return self._to_profile(match), False, None

        return None, False, CharacterRewardFailureReason.CHARACTER_NOT_FOUND

    async def _sync_to_my_domain(
        self,
        user_id: UUID,
        character: Character,
        source: str,
    ) -> None:
        """my 도메인의 user_characters 테이블에 캐릭터 소유 정보 동기화."""
        try:
            client = get_my_client()
            success, already_owned = await client.grant_character(
                user_id=user_id,
                character_id=character.id,
                character_code=character.code,
                character_name=character.name,
                character_type=character.type_label,
                character_dialog=character.dialog,
                source=source,
            )
            if success:
                logger.info(
                    "Synced character %s to my domain for user %s (already_owned=%s)",
                    character.name,
                    user_id,
                    already_owned,
                )
            else:
                logger.warning(
                    "Failed to sync character %s to my domain for user %s",
                    character.name,
                    user_id,
                )
        except Exception as e:
            # 동기화 실패해도 기존 로직은 성공으로 처리 (eventual consistency)
            logger.error(f"Error syncing to my domain: {e}")

    @staticmethod
    def _to_profile(character: Character) -> CharacterProfile:
        return CharacterProfile(
            name=character.name,
            type=str(character.type_label or "").strip(),
            dialog=str(character.dialog or character.description or "").strip(),
            match=str(character.match_label or "").strip() or None,
        )
