"""
Character Reward Consumer

Celery Chain 기반 리워드 처리 (Pipeline Step 4)
- scan_reward_task: 보상 판정만 (빠른 응답)
- persist_reward_task: 저장 task 발행 (dispatcher)
- save_ownership_task: character DB 저장
- save_my_character_task: my DB 저장 (gRPC 대신 직접)
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any
from uuid import UUID

from celery import Celery
from celery.signals import worker_ready, worker_shutdown

from domains._shared.celery.base_task import BaseTask
from domains._shared.celery.config import get_celery_settings

logger = logging.getLogger(__name__)

# Character domain Celery app
settings = get_celery_settings()
celery_app = Celery("character")
celery_app.config_from_object(settings.get_celery_config())


# ============================================================
# Worker 시작 시 캐릭터 캐시 초기화
# ============================================================


@worker_ready.connect
def init_character_cache(sender: Any, **kwargs: Any) -> None:
    """Worker 시작 시 캐릭터 캐시 초기화.

    1. DB에서 전체 캐릭터 목록 로드
    2. 로컬 캐시에 저장
    3. MQ Consumer 시작 (백그라운드)
    """
    from domains._shared.cache import get_character_cache, start_cache_consumer

    logger.info("character_cache_init_starting")

    try:
        # 1. DB에서 캐릭터 로드
        characters = _load_characters_from_db()
        if not characters:
            logger.warning("character_cache_init_empty")
            return

        # 2. 로컬 캐시에 저장
        cache = get_character_cache()
        cache.set_all(characters)

        # 3. MQ Consumer 시작 (이벤트 수신)
        broker_url = os.getenv("CELERY_BROKER_URL")
        if broker_url:
            start_cache_consumer(broker_url)
            logger.info(
                "character_cache_init_complete",
                extra={"count": cache.count()},
            )
        else:
            logger.warning("character_cache_consumer_skipped_no_broker")

    except Exception:
        logger.exception("character_cache_init_failed")


@worker_shutdown.connect
def shutdown_character_cache(sender: Any, **kwargs: Any) -> None:
    """Worker 종료 시 캐시 Consumer 정리."""
    from domains._shared.cache import stop_cache_consumer

    try:
        stop_cache_consumer()
        logger.info("character_cache_shutdown_complete")
    except Exception:
        logger.exception("character_cache_shutdown_failed")


def _load_characters_from_db() -> list[dict[str, Any]]:
    """DB에서 전체 캐릭터 목록 로드 (동기)."""
    import asyncio

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(_load_characters_async())
    finally:
        loop.close()


async def _load_characters_async() -> list[dict[str, Any]]:
    """DB에서 전체 캐릭터 목록 로드 (비동기)."""
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker

    from domains.character.core.config import get_settings
    from domains.character.repositories.character_repository import CharacterRepository

    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        repo = CharacterRepository(session)
        characters = await repo.list_all()

        return [
            {
                "id": str(char.id),
                "code": char.code,
                "name": char.name,
                "type_label": char.type_label,
                "dialog": char.dialog,
                "match_label": char.match_label,
            }
            for char in characters
        ]


# ============================================================
# Scan Chain용 Reward Task (scan.reward) - 판정만
# ============================================================


@celery_app.task(
    bind=True,
    base=BaseTask,
    name="scan.reward",
    queue="reward.character",
    max_retries=3,
    soft_time_limit=30,
    time_limit=60,
)
def scan_reward_task(
    self: BaseTask,
    prev_result: dict[str, Any],
) -> dict[str, Any]:
    """Step 4: Reward Evaluation (Chain 마지막 단계).

    보상 **판정만** 수행하고 즉시 클라이언트에게 응답합니다.
    DB 저장은 별도 task에서 비동기로 처리됩니다.

    Flow:
        1. 조건 검증 (_should_attempt_reward)
        2. 캐릭터 매칭 (DB 조회만, 저장 X)
        3. 즉시 응답 (SSE로 클라이언트에게 전달)
        4. persist_reward_task 발행 (Fire & Forget)
    """
    task_id = prev_result.get("task_id")
    user_id = prev_result.get("user_id")
    classification_result = prev_result.get("classification_result", {})
    disposal_rules = prev_result.get("disposal_rules")
    final_answer = prev_result.get("final_answer", {})
    metadata = prev_result.get("metadata", {})
    category = prev_result.get("category")

    log_ctx = {
        "task_id": task_id,
        "user_id": user_id,
        "celery_task_id": self.request.id,
        "stage": "reward",
    }
    logger.info("Scan reward task started", extra=log_ctx)

    # 1. 조건 확인
    reward = None
    if _should_attempt_reward(classification_result, disposal_rules, final_answer):
        # 2. 판정만 수행 (DB 저장 X)
        reward = _evaluate_reward_decision(
            task_id=task_id,
            user_id=user_id,
            classification_result=classification_result,
            disposal_rules_present=bool(disposal_rules),
            log_ctx=log_ctx,
        )

        # 3. DB 저장 task 발행 (Fire & Forget)
        if reward and reward.get("received") and reward.get("character_id"):
            try:
                persist_reward_task.delay(
                    user_id=user_id,
                    character_id=reward["character_id"],
                    character_code=reward.get("character_code", ""),
                    character_name=reward.get("name", ""),
                    character_type=reward.get("character_type"),
                    character_dialog=reward.get("dialog"),
                    source="scan",
                    task_id=task_id,
                )
                logger.info(
                    "Persist reward task dispatched",
                    extra={**log_ctx, "character_id": reward["character_id"]},
                )
            except Exception:
                logger.exception("Failed to dispatch persist_reward_task", extra=log_ctx)

    # 4. 최종 결과 구성 (내부용 필드 제거)
    reward_response = None
    if reward:
        reward_response = {
            "received": reward.get("received", False),
            "already_owned": reward.get("already_owned", False),
            "name": reward.get("name"),
            "dialog": reward.get("dialog"),
            "match_reason": reward.get("match_reason"),
            "character_type": reward.get("character_type"),
            "type": reward.get("type"),
        }

    result = {
        **prev_result,
        "reward": reward_response,
    }

    logger.info(
        "scan_task_completed",
        extra={
            "event_type": "scan_completed",
            "task_id": task_id,
            "user_id": user_id,
            "category": category,
            "duration_total_ms": metadata.get("duration_total_ms"),
            "duration_vision_ms": metadata.get("duration_vision_ms"),
            "duration_rule_ms": metadata.get("duration_rule_ms"),
            "duration_answer_ms": metadata.get("duration_answer_ms"),
            "has_disposal_rules": disposal_rules is not None,
            "has_reward": reward_response is not None,
            "reward_received": reward_response.get("received") if reward_response else None,
        },
    )

    # 커스텀 이벤트 발행 (task-succeeded 이벤트가 수신되지 않는 문제 우회)
    # Celery의 send_event()는 celeryev exchange로 이벤트를 발행함
    try:
        self.send_event(
            "task-result",
            result=result,
            task_id=task_id,
            root_id=task_id,
        )
        logger.debug("task_result_event_sent", extra={"task_id": task_id})
    except Exception as e:
        logger.warning("task_result_event_failed", extra={"task_id": task_id, "error": str(e)})

    return result


# ============================================================
# Persist Reward Task - 저장 task 발행 (dispatcher)
# ============================================================


@celery_app.task(
    bind=True,
    base=BaseTask,
    name="character.persist_reward",
    queue="reward.persist",
    max_retries=3,
    soft_time_limit=10,
    time_limit=20,
)
def persist_reward_task(
    self: BaseTask,
    user_id: str,
    character_id: str,
    character_code: str,
    character_name: str,
    character_type: str | None,
    character_dialog: str | None,
    source: str,
    task_id: str | None = None,
) -> dict[str, Any]:
    """저장 task 발행 (dispatcher).

    2개의 저장 task를 동시에 발행합니다 (Fire & Forget):
    1. save_ownership_task → character.character_ownerships
    2. save_my_character_task → my.user_characters

    둘 다 독립적으로 재시도됩니다.
    """
    log_ctx = {
        "task_id": task_id,
        "user_id": user_id,
        "character_id": character_id,
        "source": source,
        "celery_task_id": self.request.id,
    }
    logger.info("Persist reward dispatcher started", extra=log_ctx)

    dispatched = {"ownership": False, "my_character": False}

    # 1. character_ownerships 저장 task 발행
    try:
        save_ownership_task.delay(
            user_id=user_id,
            character_id=character_id,
            source=source,
        )
        dispatched["ownership"] = True
        logger.info("save_ownership_task dispatched", extra=log_ctx)
    except Exception:
        logger.exception("Failed to dispatch save_ownership_task", extra=log_ctx)

    # 2. my.user_characters 저장 task 발행
    try:
        save_my_character_task.delay(
            user_id=user_id,
            character_id=character_id,
            character_code=character_code,
            character_name=character_name,
            character_type=character_type,
            character_dialog=character_dialog,
            source=source,
        )
        dispatched["my_character"] = True
        logger.info("save_my_character_task dispatched", extra=log_ctx)
    except Exception:
        logger.exception("Failed to dispatch save_my_character_task", extra=log_ctx)

    return {"dispatched": dispatched}


# ============================================================
# Save Ownership Task - character DB 저장
# ============================================================


@celery_app.task(
    bind=True,
    base=BaseTask,
    name="character.save_ownership",
    queue="reward.persist",
    max_retries=5,
    soft_time_limit=30,
    time_limit=60,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
)
def save_ownership_task(
    self: BaseTask,
    user_id: str,
    character_id: str,
    source: str,
) -> dict[str, Any]:
    """character.character_ownerships 저장.

    Idempotent: 이미 소유한 경우 skip.
    """
    log_ctx = {
        "user_id": user_id,
        "character_id": character_id,
        "source": source,
        "celery_task_id": self.request.id,
    }
    logger.info("Save ownership task started", extra=log_ctx)

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(
                _save_ownership_async(
                    user_id=user_id,
                    character_id=character_id,
                    source=source,
                )
            )
        finally:
            loop.close()

        logger.info("Save ownership completed", extra={**log_ctx, **result})
        return result

    except Exception:
        logger.exception("Save ownership failed", extra=log_ctx)
        raise


async def _save_ownership_async(
    user_id: str,
    character_id: str,
    source: str,
) -> dict[str, Any]:
    """character.character_ownerships 멱등적 UPSERT.

    ON CONFLICT DO NOTHING을 사용하여 여러 번 호출해도 안전합니다.
    SELECT 없이 바로 INSERT 시도하므로 DB 조회 1회만 발생합니다.
    """
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker

    from domains.character.core.config import get_settings
    from domains.character.repositories.ownership_repository import CharacterOwnershipRepository

    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        ownership_repo = CharacterOwnershipRepository(session)

        # 멱등적 UPSERT: 이미 존재하면 무시
        inserted = await ownership_repo.insert_or_ignore(
            user_id=UUID(user_id),
            character_id=UUID(character_id),
            source=source,
        )

        return {
            "saved": inserted,
            "reason": None if inserted else "already_owned",
        }


# ============================================================
# Save My Character Task - my DB 저장 (gRPC 대신 직접)
# ============================================================


@celery_app.task(
    bind=True,
    base=BaseTask,
    name="character.save_my_character",
    queue="my.sync",
    max_retries=5,
    soft_time_limit=30,
    time_limit=60,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
)
def save_my_character_task(
    self: BaseTask,
    user_id: str,
    character_id: str,
    character_code: str,
    character_name: str,
    character_type: str | None,
    character_dialog: str | None,
    source: str,
) -> dict[str, Any]:
    """my.user_characters 저장 (gRPC 대신 직접 INSERT).

    Idempotent: upsert 로직 (이미 소유한 경우 상태 업데이트).
    """
    log_ctx = {
        "user_id": user_id,
        "character_id": character_id,
        "character_name": character_name,
        "source": source,
        "celery_task_id": self.request.id,
    }
    logger.info("Save my character task started", extra=log_ctx)

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(
                _save_my_character_async(
                    user_id=user_id,
                    character_id=character_id,
                    character_code=character_code,
                    character_name=character_name,
                    character_type=character_type,
                    character_dialog=character_dialog,
                    source=source,
                )
            )
        finally:
            loop.close()

        logger.info("Save my character completed", extra={**log_ctx, **result})
        return result

    except Exception:
        logger.exception("Save my character failed", extra=log_ctx)
        raise


async def _save_my_character_async(
    user_id: str,
    character_id: str,
    character_code: str,
    character_name: str,
    character_type: str | None,
    character_dialog: str | None,
    source: str,
) -> dict[str, Any]:
    """my.user_characters INSERT (직접 DB 접근)."""
    import os

    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker

    from domains.my.repositories.user_character_repository import UserCharacterRepository

    # my 도메인 DB URL (환경변수에서)
    my_db_url = os.getenv(
        "MY_DATABASE_URL",
        "postgresql+asyncpg://postgres:postgres@localhost:5432/my",
    )
    engine = create_async_engine(my_db_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        repo = UserCharacterRepository(session)

        # upsert: 이미 소유한 경우 상태 업데이트
        user_char = await repo.grant_character(
            user_id=UUID(user_id),
            character_id=UUID(character_id),
            character_code=character_code,
            character_name=character_name,
            character_type=character_type,
            character_dialog=character_dialog,
            source=source,
        )
        await session.commit()

        return {
            "saved": True,
            "user_character_id": str(user_char.id),
        }


# ============================================================
# 판정 로직 (DB 저장 없음)
# ============================================================


def _should_attempt_reward(
    classification_result: dict[str, Any],
    disposal_rules: dict | None,
    final_answer: dict[str, Any],
) -> bool:
    """리워드 평가 조건 확인."""
    import os

    reward_enabled = os.getenv("REWARD_FEATURE_ENABLED", "true").lower() == "true"
    if not reward_enabled:
        return False

    classification = classification_result.get("classification", {})
    major = classification.get("major_category", "").strip()
    middle = classification.get("middle_category", "").strip()

    if not major or not middle:
        return False

    if major != "재활용폐기물":
        return False

    if not disposal_rules:
        return False

    insufficiencies = final_answer.get("insufficiencies", [])
    for entry in insufficiencies:
        if isinstance(entry, str) and entry.strip():
            return False
        elif entry:
            return False

    return True


def _evaluate_reward_decision(
    task_id: str,
    user_id: str,
    classification_result: dict[str, Any],
    disposal_rules_present: bool,
    log_ctx: dict,
) -> dict[str, Any] | None:
    """캐릭터 매칭 판정 (DB 저장 없음)."""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(
                _match_character_async(
                    user_id=user_id,
                    classification_result=classification_result,
                    disposal_rules_present=disposal_rules_present,
                )
            )
        finally:
            loop.close()

        logger.info(
            "Reward decision completed",
            extra={
                **log_ctx,
                "received": result.get("received") if result else False,
                "character_name": result.get("name") if result else None,
            },
        )
        return result

    except Exception:
        logger.exception("Reward decision failed", extra=log_ctx)
        return None


async def _match_character_async(
    user_id: str,
    classification_result: dict[str, Any],
    disposal_rules_present: bool,
) -> dict[str, Any]:
    """캐릭터 매칭 수행 (로컬 캐시 사용, DB 조회 없음).

    로컬 캐시에서 캐릭터 목록을 가져와 매칭을 수행합니다.
    DB 저장은 멱등 UPSERT로 처리되므로 소유권 확인이 불필요합니다.
    """
    from domains._shared.cache import get_character_cache
    from domains.character.schemas.reward import (
        CharacterRewardRequest,
        CharacterRewardSource,
        ClassificationSummary,
    )
    from domains.character.services.evaluators import get_evaluator

    classification = classification_result.get("classification", {})
    situation_tags = classification_result.get("situation_tags", [])

    # 로컬 캐시에서 캐릭터 목록 조회 (DB 조회 없음)
    cache = get_character_cache()
    if not cache.is_initialized:
        logger.warning("character_cache_not_initialized")
        return {"received": False, "reason": "cache_not_initialized"}

    cached_characters = cache.get_all()
    if not cached_characters:
        return {"received": False, "reason": "no_characters"}

    evaluator = get_evaluator(CharacterRewardSource.SCAN)
    if evaluator is None:
        return {"received": False, "reason": "no_evaluator"}

    request = CharacterRewardRequest(
        source=CharacterRewardSource.SCAN,
        user_id=UUID(user_id),
        task_id="",
        classification=ClassificationSummary(
            major_category=classification.get("major_category", ""),
            middle_category=classification.get("middle_category", ""),
            minor_category=classification.get("minor_category"),
        ),
        situation_tags=situation_tags,
        disposal_rules_present=disposal_rules_present,
        insufficiencies_present=False,
    )

    # 캐시된 캐릭터로 평가 (evaluator는 CachedCharacter 객체도 처리 가능)
    eval_result = evaluator.evaluate(request, cached_characters)

    if not eval_result.should_evaluate or not eval_result.matches:
        return {"received": False, "reason": "no_match"}

    matched_character = eval_result.matches[0]

    # 소유권 확인 없이 항상 received=True 반환
    # 실제 저장은 멱등 UPSERT로 처리 (이미 있으면 무시됨)
    return {
        "received": True,
        "already_owned": False,  # UPSERT에서 판단됨
        "character_id": str(matched_character.id),
        "character_code": matched_character.code,
        "name": matched_character.name,
        "dialog": matched_character.dialog,
        "match_reason": eval_result.match_reason,
        "character_type": matched_character.type_label,
        "type": str(matched_character.type_label or "").strip(),
    }


# ============================================================
# Legacy Task (하위 호환성)
# ============================================================


@celery_app.task(
    bind=True,
    name="character.reward.process",
    queue="reward.character",
    max_retries=3,
    soft_time_limit=30,
    time_limit=60,
)
def reward_consumer_task(
    self,
    task_id: str,
    user_id: str,
    classification: dict[str, Any],
    situation_tags: list[str],
    disposal_rules_present: bool,
) -> dict[str, Any]:
    """Legacy: Fire & Forget 방식의 reward task.

    DEPRECATED: Chain 방식으로 전환됨.
    """
    logger.warning(
        "Legacy reward consumer task called",
        extra={"task_id": task_id, "user_id": user_id},
    )

    result = _evaluate_reward_decision(
        task_id=task_id,
        user_id=user_id,
        classification_result={
            "classification": classification,
            "situation_tags": situation_tags,
        },
        disposal_rules_present=disposal_rules_present,
        log_ctx={"task_id": task_id, "user_id": user_id},
    )

    if result and result.get("received") and result.get("character_id"):
        persist_reward_task.delay(
            user_id=user_id,
            character_id=result["character_id"],
            character_code=result.get("character_code", ""),
            character_name=result.get("name", ""),
            character_type=result.get("character_type"),
            character_dialog=result.get("dialog"),
            source="scan",
            task_id=task_id,
        )

    return result or {"received": False, "reason": "evaluation_failed"}
