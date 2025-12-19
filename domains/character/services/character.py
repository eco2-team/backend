from __future__ import annotations

import logging
from typing import Sequence
from uuid import UUID

from fastapi import Depends
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from domains.character.core.constants import (
    DEFAULT_CHARACTER_NAME,
    MATCH_REASON_UNDEFINED,
    RECYCLABLE_WASTE_CATEGORY,
    REWARD_SOURCE_SCAN,
)
from domains.character.database.session import get_db_session
from domains.character.exceptions import CatalogEmptyError
from domains.character.metrics import REWARD_EVALUATION_TOTAL, REWARD_GRANTED_TOTAL
from domains.character.models import Character
from domains.character.repositories import CharacterOwnershipRepository, CharacterRepository
from domains.character.rpc.my_client import get_my_client
from domains.character.schemas.catalog import CharacterProfile
from domains.character.schemas.reward import (
    CharacterRewardFailureReason,
    CharacterRewardRequest,
    CharacterRewardResponse,
    CharacterRewardSource,
    ClassificationSummary,
)

logger = logging.getLogger(__name__)


class CharacterService:
    def __init__(self, session: AsyncSession = Depends(get_db_session)):
        self.session = session
        self.character_repo = CharacterRepository(session)
        self.ownership_repo = CharacterOwnershipRepository(session)

    async def catalog(self) -> list[CharacterProfile]:
        characters = await self.character_repo.list_all()
        if not characters:
            raise CatalogEmptyError()
        return [self._to_profile(character) for character in characters]

    async def get_default_character(self) -> Character | None:
        """기본 캐릭터(이코) 정보 조회. my 도메인에서 사용."""
        return await self.character_repo.get_by_name(DEFAULT_CHARACTER_NAME)

    async def metrics(self) -> dict:
        """Return character service metrics from database."""
        catalog_size = len(await self.character_repo.list_all())
        return {
            "catalog_size": catalog_size,
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
            and classification.major_category.strip() == RECYCLABLE_WASTE_CATEGORY
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

    async def _match_characters(self, classification: ClassificationSummary) -> list[Character]:
        match_label = self._resolve_match_label(classification)
        if not match_label:
            return []
        return await self.character_repo.list_by_match_label(match_label)

    @staticmethod
    def _resolve_match_label(classification: ClassificationSummary) -> str | None:
        major = (classification.major_category or "").strip()
        middle = (classification.middle_category or "").strip()
        if major == RECYCLABLE_WASTE_CATEGORY:
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
        return MATCH_REASON_UNDEFINED

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

            try:
                await self._grant_and_sync(
                    user_id=user_id, character=match, source=REWARD_SOURCE_SCAN
                )
                return self._to_profile(match), False, None
            except IntegrityError:
                # Race condition: 동시 요청으로 인한 중복 INSERT 시도
                # UniqueConstraint 위반 → 이미 소유한 것으로 처리
                await self.session.rollback()
                logger.info(
                    "Concurrent ownership grant detected",
                    extra={"user_id": str(user_id), "character_id": str(match.id)},
                )
                return self._to_profile(match), True, None

        return None, False, CharacterRewardFailureReason.CHARACTER_NOT_FOUND

    async def _grant_and_sync(
        self,
        user_id: UUID,
        character: Character,
        source: str,
    ) -> None:
        """캐릭터 소유권 저장 및 my 도메인 동기화.

        Transaction Semantics:
            1. character 스키마에 ownership 저장 후 commit
            2. my 도메인으로 gRPC 동기화 (best-effort)

        Consistency Model:
            - gRPC 동기화 실패해도 로컬 ownership은 유지됨 (eventual consistency)
            - my 도메인과의 정합성은 후속 동기화 배치로 보장
            - 동시 요청 시 IntegrityError는 호출자가 처리

        Raises:
            IntegrityError: 동시 요청으로 인한 중복 ownership 시도 시
        """
        # 1. character.character_ownerships에 저장
        await self.ownership_repo.upsert_owned(
            user_id=user_id,
            character=character,
            source=source,
        )
        await self.session.commit()

        # 2. my 도메인에 gRPC로 동기화 (best-effort, 실패해도 로컬 저장은 유지)
        await self._sync_to_my_domain(user_id=user_id, character=character, source=source)

    async def _grant_and_sync(
        self,
        user_id: UUID,
        character: Character,
        source: str,
    ) -> None:
        """캐릭터 소유권 저장 및 my 도메인 동기화 (공통 로직)."""
        # 1. character.character_ownerships에 저장
        await self.ownership_repo.upsert_owned(
            user_id=user_id,
            character=character,
            source=source,
        )
        await self.session.commit()

        # 2. my 도메인에 gRPC로 동기화
        await self._sync_to_my_domain(user_id=user_id, character=character, source=source)

    async def _sync_to_my_domain(
        self,
        user_id: UUID,
        character: Character,
        source: str,
    ) -> None:
        """my 도메인의 user_characters 테이블에 캐릭터 소유 정보 동기화."""
        log_ctx = {
            "user_id": str(user_id),
            "character_id": str(character.id),
            "character_name": character.name,
            "source": source,
        }
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
                    "Synced character to my domain",
                    extra={**log_ctx, "already_owned": already_owned},
                )
            else:
                logger.warning(
                    "Failed to sync character to my domain",
                    extra=log_ctx,
                )
        except Exception:
            # 동기화 실패해도 기존 로직은 성공으로 처리 (eventual consistency)
            logger.exception("Error syncing to my domain", extra=log_ctx)

    @staticmethod
    def _to_profile(character: Character) -> CharacterProfile:
        return CharacterProfile(
            name=character.name,
            type=str(character.type_label or "").strip(),
            dialog=str(character.dialog or character.description or "").strip(),
            match=str(character.match_label or "").strip() or None,
        )
