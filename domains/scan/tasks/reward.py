"""
Scan Reward Task

Celery Chain 기반 리워드 처리 (Pipeline Step 4)
- scan_reward_task: 보상 판정만 (빠른 응답)

DB 저장은 character 도메인의 persist_reward_task에서 비동기로 처리됩니다.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any
from uuid import UUID

from domains._shared.celery.base_task import BaseTask
from domains.scan.celery_app import celery_app

logger = logging.getLogger(__name__)


# ============================================================
# Scan Chain용 Reward Task (scan.reward) - 판정만
# ============================================================


@celery_app.task(
    bind=True,
    base=BaseTask,
    name="scan.reward",
    queue="scan.reward",
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
        2. 캐릭터 매칭 (로컬 캐시 사용, DB 저장 X)
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

        # 3. DB 저장 task 발행 (Fire & Forget) - 각 도메인으로 직접 발급
        #    send_task()를 사용하여 task import 없이 이름으로 호출
        if reward and reward.get("received") and reward.get("character_id"):
            dispatched = {"character": False, "my": False}

            # 3-1. character.save_ownership → character.reward 큐
            try:
                celery_app.send_task(
                    "character.save_ownership",
                    kwargs={
                        "user_id": user_id,
                        "character_id": reward["character_id"],
                        "source": "scan",
                    },
                    queue="character.reward",
                )
                dispatched["character"] = True
                logger.info("save_ownership_task dispatched", extra=log_ctx)
            except Exception:
                logger.exception("Failed to dispatch save_ownership_task", extra=log_ctx)

            # 3-2. my.save_character → my.reward 큐
            try:
                celery_app.send_task(
                    "my.save_character",
                    kwargs={
                        "user_id": user_id,
                        "character_id": reward["character_id"],
                        "character_code": reward.get("character_code", ""),
                        "character_name": reward.get("name", ""),
                        "character_type": reward.get("character_type"),
                        "character_dialog": reward.get("dialog"),
                        "source": "scan",
                    },
                    queue="my.reward",
                )
                dispatched["my"] = True
                logger.info("save_my_character_task dispatched", extra=log_ctx)
            except Exception:
                logger.exception("Failed to dispatch save_my_character_task", extra=log_ctx)

            logger.info(
                "Reward storage tasks dispatched",
                extra={**log_ctx, "character_id": reward["character_id"], "dispatched": dispatched},
            )

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
# 판정 로직 (DB 저장 없음, 로컬 캐시 사용)
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
    """캐릭터 매칭만 수행 (DB 저장 없음, 로컬 캐시 우선 사용)."""
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker

    from domains._shared.cache import get_character_cache
    from domains.character.core.config import get_settings
    from domains.character.repositories.ownership_repository import CharacterOwnershipRepository
    from domains.character.schemas.reward import (
        CharacterRewardRequest,
        CharacterRewardSource,
        ClassificationSummary,
    )
    from domains.character.services.evaluators import get_evaluator

    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    classification = classification_result.get("classification", {})
    situation_tags = classification_result.get("situation_tags", [])

    # 로컬 캐시에서 캐릭터 목록 조회 (DB 조회 최소화)
    cache = get_character_cache()
    characters = cache.list_all()

    if not characters:
        # 캐시가 비어있으면 DB에서 직접 조회 (fallback)
        from domains.character.repositories.character_repository import CharacterRepository

        async with async_session() as session:
            character_repo = CharacterRepository(session)
            characters = await character_repo.list_all()

    if not characters:
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

    eval_result = evaluator.evaluate(request, characters)

    if not eval_result.should_evaluate or not eval_result.matches:
        return {"received": False, "reason": "no_match"}

    matched_character = eval_result.matches[0]

    # 소유권 체크는 DB에서 (캐시에 없음)
    async with async_session() as session:
        ownership_repo = CharacterOwnershipRepository(session)
        existing = await ownership_repo.get_by_user_and_character(
            user_id=UUID(user_id), character_id=matched_character.id
        )

    return {
        "received": not existing,
        "already_owned": existing is not None,
        "character_id": str(matched_character.id),
        "character_code": matched_character.code,
        "name": matched_character.name,
        "dialog": matched_character.dialog,
        "match_reason": eval_result.match_reason,
        "character_type": matched_character.type_label,
        "type": str(matched_character.type_label or "").strip(),
    }
