from __future__ import annotations

import logging
import os
from contextlib import nullcontext
from typing import Sequence
from uuid import UUID

from fastapi import Depends
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from domains.character.core.cache import CATALOG_KEY, get_cached, set_cached
from domains.character.core.constants import DEFAULT_CHARACTER_NAME
from domains.character.core.tracing import get_tracer
from domains.character.database.session import get_db_session
from domains.character.exceptions import CatalogEmptyError
from domains.character.metrics import REWARD_EVALUATION_TOTAL, REWARD_GRANTED_TOTAL
from domains.character.models import Character
from domains.character.repositories import CharacterOwnershipRepository, CharacterRepository
from domains.character.schemas.catalog import CharacterProfile
from domains.character.schemas.reward import (
    CharacterRewardFailureReason,
    CharacterRewardRequest,
    CharacterRewardResponse,
)
from domains.character.services.evaluators import EvaluationResult, get_evaluator

logger = logging.getLogger(__name__)


def _publish_cache_event(event_type: str, character: Character | None = None) -> None:
    """Worker 로컬 캐시 동기화를 위한 MQ 이벤트 발행.

    Args:
        event_type: "upsert" 또는 "delete"
        character: 대상 캐릭터 (delete 시 character_id만 사용)
    """
    broker_url = os.getenv("CELERY_BROKER_URL")
    if not broker_url:
        logger.debug("cache_event_skipped_no_broker")
        return

    try:
        from domains._shared.cache import get_cache_publisher

        publisher = get_cache_publisher(broker_url)

        if event_type == "upsert" and character:
            publisher.publish_upsert(
                {
                    "id": str(character.id),
                    "code": character.code,
                    "name": character.name,
                    "type_label": character.type_label,
                    "dialog": character.dialog,
                    "match_label": character.match_label,
                }
            )
        elif event_type == "delete" and character:
            publisher.publish_delete(str(character.id))

    except Exception:
        logger.exception("cache_event_publish_failed", extra={"event_type": event_type})


class CharacterService:
    def __init__(self, session: AsyncSession = Depends(get_db_session)):
        self.session = session
        self.character_repo = CharacterRepository(session)
        self.ownership_repo = CharacterOwnershipRepository(session)

    @classmethod
    def create_for_test(
        cls,
        session: AsyncSession,
        character_repo: CharacterRepository | None = None,
        ownership_repo: CharacterOwnershipRepository | None = None,
    ) -> "CharacterService":
        """테스트용 팩토리 메서드.

        __new__를 우회하지 않고 테스트 의존성을 주입합니다.

        Args:
            session: DB 세션
            character_repo: 캐릭터 레포지토리 (None이면 기본 생성)
            ownership_repo: 소유권 레포지토리 (None이면 기본 생성)

        Returns:
            CharacterService 인스턴스
        """
        service = cls.__new__(cls)
        service.session = session
        service.character_repo = character_repo or CharacterRepository(session)
        service.ownership_repo = ownership_repo or CharacterOwnershipRepository(session)
        return service

    async def catalog(self) -> list[CharacterProfile]:
        """캐릭터 카탈로그 조회 (캐시 적용).

        Cache Strategy:
            1. Redis에서 캐시 조회 (hit → 즉시 반환)
            2. Cache miss → DB 조회 후 캐시 저장
            3. Redis 실패 → Graceful degradation (DB 직접 조회)
        """
        # 1. 캐시 조회
        cached = await get_cached(CATALOG_KEY)
        if cached is not None:
            return [CharacterProfile(**item) for item in cached]

        # 2. DB 조회
        characters = await self.character_repo.list_all()
        if not characters:
            raise CatalogEmptyError()

        profiles = [self._to_profile(character) for character in characters]

        # 3. 캐시 저장 (비동기, 실패해도 무시)
        await set_cached(CATALOG_KEY, [p.model_dump() for p in profiles])

        return profiles

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
        """캐릭터 리워드 평가 및 지급.

        Strategy 패턴으로 소스별 평가 로직을 분리합니다.
        - SCAN: ScanRewardEvaluator (source_label: "scan-reward")
        - QUEST: QuestRewardEvaluator (향후 확장)

        Jaeger에서 다음 span 구조로 추적됨:
            evaluate_reward
            ├── match_characters (캐릭터 매칭)
            │   └── asyncpg: SELECT characters...
            └── apply_reward (소유권 지급)
                ├── asyncpg: SELECT/INSERT ownerships...
                └── grpc: my.UserCharacterService/Grant
        """
        tracer = get_tracer(__name__)
        user_id_str = str(payload.user_id)

        with tracer.start_as_current_span("evaluate_reward") if tracer else nullcontext() as span:
            if span:
                span.set_attribute("user_id", user_id_str)
                span.set_attribute("source", payload.source.value)

            logger.info(
                "Reward evaluation started",
                extra={"user_id": user_id_str, "source": payload.source.value},
            )

            # Strategy 패턴: 소스에 맞는 evaluator 조회
            evaluator = get_evaluator(payload.source)
            if evaluator is None:
                logger.warning(
                    "No evaluator registered for source",
                    extra={"source": payload.source.value},
                )
                self._record_reward_metrics(source=payload.source.value, status="no_evaluator")
                return self._to_reward_response(None, False, False, None)

            # 1. 캐릭터 목록 조회 및 평가
            with tracer.start_as_current_span("match_characters") if tracer else nullcontext():
                # Service에서 캐릭터 조회 후 Evaluator에 전달 (책임 분리)
                characters = await self.character_repo.list_all()
                eval_result = evaluator.evaluate(payload, characters)

            # 2. 평가 결과 처리
            reward_profile, already_owned, failure_reason, received = (
                await self._process_evaluation(payload.user_id, eval_result, tracer)
            )

            # 3. 메트릭 기록
            self._record_reward_metrics(
                source=payload.source.value,
                eval_result=eval_result,
                received=received,
                already_owned=already_owned,
                failure_reason=failure_reason,
                reward_profile=reward_profile,
            )

            # 4. span에 결과 기록
            if span:
                span.set_attribute("received", received)
                span.set_attribute("already_owned", already_owned)
                if reward_profile:
                    span.set_attribute("character_name", reward_profile.name)

            logger.info(
                "Reward evaluation completed",
                extra={
                    "user_id": user_id_str,
                    "received": received,
                    "already_owned": already_owned,
                    "character_name": reward_profile.name if reward_profile else None,
                },
            )

            return self._to_reward_response(
                reward_profile, already_owned, received, eval_result.match_reason
            )

    async def _process_evaluation(
        self,
        user_id: UUID,
        eval_result: EvaluationResult,
        tracer,
    ) -> tuple[CharacterProfile | None, bool, CharacterRewardFailureReason | None, bool]:
        """평가 결과를 처리하고 리워드를 지급합니다.

        Returns:
            (reward_profile, already_owned, failure_reason, received)
        """
        if not eval_result.should_evaluate or not eval_result.matches:
            return None, False, None, False

        # 리워드 지급 span
        with tracer.start_as_current_span("apply_reward") if tracer else nullcontext():
            reward_profile, already_owned, failure_reason = await self._apply_reward(
                user_id=user_id,
                matches=eval_result.matches,
                source_label=eval_result.source_label,  # Strategy에서 제공
            )

        received = failure_reason is None and reward_profile is not None and not already_owned
        return reward_profile, already_owned, failure_reason, received

    @staticmethod
    def _determine_reward_status(
        eval_result: EvaluationResult | None,
        received: bool,
        already_owned: bool,
        failure_reason: CharacterRewardFailureReason | None,
    ) -> str:
        """리워드 처리 결과에 따른 상태 문자열 결정."""
        if eval_result and not eval_result.should_evaluate:
            return "skipped"
        if eval_result and not eval_result.matches:
            return "no_match"
        if already_owned:
            return "already_owned"
        if failure_reason:
            return f"failed_{failure_reason.value}"
        if received:
            return "success"
        return "failed"

    @staticmethod
    def _record_reward_metrics(
        source: str,
        eval_result: EvaluationResult | None = None,
        received: bool = False,
        already_owned: bool = False,
        failure_reason: CharacterRewardFailureReason | None = None,
        reward_profile: CharacterProfile | None = None,
        status: str | None = None,
    ) -> None:
        """리워드 평가 메트릭 기록."""
        if status is None:
            status = CharacterService._determine_reward_status(
                eval_result, received, already_owned, failure_reason
            )

        REWARD_EVALUATION_TOTAL.labels(status=status, source=source).inc()

        if received and reward_profile:
            REWARD_GRANTED_TOTAL.labels(
                character_name=reward_profile.name,
                type=reward_profile.type or "unknown",
            ).inc()

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

    async def _apply_reward(
        self,
        user_id: UUID,
        matches: Sequence[Character],
        source_label: str,
    ) -> tuple[CharacterProfile | None, bool, CharacterRewardFailureReason | None]:
        """매칭된 캐릭터 중 첫 번째로 지급 가능한 캐릭터를 지급합니다.

        Args:
            user_id: 사용자 ID
            matches: 매칭된 캐릭터 목록 (우선순위 순)
            source_label: 리워드 소스 식별자 (Strategy에서 제공)

        Returns:
            (reward_profile, already_owned, failure_reason)
        """
        for match in matches:
            existing = await self.ownership_repo.get_by_user_and_character(
                user_id=user_id, character_id=match.id
            )
            if existing:
                # my 도메인과의 정합성 보장을 위해 sync 재시도 (idempotent)
                self._sync_to_my_domain(user_id=user_id, character=match, source=source_label)
                return self._to_profile(match), True, None

            try:
                await self._grant_and_sync(
                    user_id=user_id,
                    character=match,
                    source=source_label,  # Strategy에서 제공된 source 사용
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
        # 1. character.character_ownerships에 저장 (SELECT 없이 직접 INSERT)
        await self.ownership_repo.insert_owned(
            user_id=user_id,
            character=character,
            source=source,
        )
        await self.session.commit()

        # 2. my 도메인에 Celery task로 비동기 동기화 (Fire & Forget)
        self._sync_to_my_domain(user_id=user_id, character=character, source=source)

    def _sync_to_my_domain(
        self,
        user_id: UUID,
        character: Character,
        source: str,
    ) -> None:
        """my 도메인의 user_characters 테이블에 캐릭터 소유 정보 비동기 동기화.

        Celery task로 발행하여 gRPC 호출을 비동기로 처리합니다.
        character.character_ownerships 저장 후 즉시 반환되며,
        my 도메인 동기화는 별도 worker에서 처리됩니다.

        Consistency Model:
            - 로컬 ownership 저장은 동기로 완료됨
            - my 도메인 동기화는 비동기 (eventual consistency)
            - 실패 시 Celery가 자동 재시도 (max 5회, exponential backoff)
        """
        from domains.character.consumers.sync_my import sync_to_my_task

        log_ctx = {
            "user_id": str(user_id),
            "character_id": str(character.id),
            "character_name": character.name,
            "source": source,
        }

        try:
            sync_to_my_task.delay(
                user_id=str(user_id),
                character_id=str(character.id),
                character_code=character.code,
                character_name=character.name,
                character_type=character.type_label,
                character_dialog=character.dialog,
                source=source,
            )
            logger.info(
                "Sync to my domain task dispatched",
                extra=log_ctx,
            )
        except Exception:
            # Task 발행 실패해도 로컬 ownership은 유지 (eventual consistency)
            # 후속 배치 동기화로 복구 가능
            logger.exception("Failed to dispatch sync task", extra=log_ctx)

    @staticmethod
    def _to_profile(character: Character) -> CharacterProfile:
        return CharacterProfile(
            name=character.name,
            type=str(character.type_label or "").strip(),
            dialog=str(character.dialog or character.description or "").strip(),
            match=str(character.match_label or "").strip() or None,
        )
