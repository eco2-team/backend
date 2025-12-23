"""
Scan Reward Task

Celery Chain 기반 리워드 처리 (Pipeline Step 4)
- scan_reward_task: 보상 dispatch (character.match 호출 → fire & forget)

매칭은 character 도메인에서 처리하고, 결과를 받아 SSE로 반환합니다.
DB 저장은 character/my 도메인의 task에서 비동기로 처리됩니다.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from domains._shared.celery.base_task import BaseTask
from domains.scan.celery_app import celery_app

logger = logging.getLogger(__name__)

# 매칭 결과 대기 타임아웃 (초)
MATCH_TIMEOUT = int(os.getenv("CHARACTER_MATCH_TIMEOUT", "10"))


# ============================================================
# Scan Chain용 Reward Task (scan.reward) - Dispatch 역할
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

    보상 매칭을 character 도메인에 위임하고 결과를 받아 응답합니다.
    DB 저장은 별도 task에서 비동기로 처리됩니다.

    Flow:
        1. 조건 검증 (_should_attempt_reward)
        2. character.match 호출 (동기 대기) → 매칭 결과
        3. 즉시 응답 (SSE로 클라이언트에게 전달)
        4. character.save_ownership, my.save_character 발행 (Fire & Forget)
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
        # 2. character.match 호출 (동기 대기)
        reward = _dispatch_character_match(
            user_id=user_id,
            classification_result=classification_result,
            disposal_rules_present=bool(disposal_rules),
            log_ctx=log_ctx,
        )

        # 3. DB 저장 task 발행 (Fire & Forget)
        if reward and reward.get("received") and reward.get("character_id"):
            _dispatch_save_tasks(
                user_id=user_id,
                reward=reward,
                log_ctx=log_ctx,
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
            "reward_received": (reward_response.get("received") if reward_response else None),
        },
    )

    # 커스텀 이벤트 발행 (task-succeeded 이벤트가 수신되지 않는 문제 우회)
    try:
        self.send_event(
            "task-result",
            result=result,
            task_id=task_id,
            root_id=task_id,
        )
        logger.debug("task_result_event_sent", extra={"task_id": task_id})
    except Exception as e:
        logger.warning(
            "task_result_event_failed",
            extra={"task_id": task_id, "error": str(e)},
        )

    return result


# ============================================================
# Helper Functions
# ============================================================


def _should_attempt_reward(
    classification_result: dict[str, Any],
    disposal_rules: dict | None,
    final_answer: dict[str, Any],
) -> bool:
    """리워드 평가 조건 확인."""
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


def _dispatch_character_match(
    user_id: str,
    classification_result: dict[str, Any],
    disposal_rules_present: bool,
    log_ctx: dict,
) -> dict[str, Any] | None:
    """character.match task 호출 (동기 대기).

    character-worker에서 로컬 캐시를 사용해 매칭 수행.
    """
    try:
        # send_task로 character.match 호출 (import 없이 이름으로)
        async_result = celery_app.send_task(
            "character.match",
            kwargs={
                "user_id": user_id,
                "classification_result": classification_result,
                "disposal_rules_present": disposal_rules_present,
            },
            queue="character.match",  # 빠른 응답용 전용 큐
        )

        # 동기 대기 (타임아웃 설정)
        result = async_result.get(timeout=MATCH_TIMEOUT)

        logger.info(
            "Character match completed",
            extra={
                **log_ctx,
                "received": result.get("received") if result else False,
                "character_name": result.get("name") if result else None,
            },
        )
        return result

    except Exception:
        logger.exception("Character match failed", extra=log_ctx)
        return None


def _dispatch_save_tasks(
    user_id: str,
    reward: dict[str, Any],
    log_ctx: dict,
) -> None:
    """DB 저장 task 발행 (Fire & Forget)."""
    dispatched = {"character": False, "my": False}

    # character.save_ownership → character.reward 큐
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

    # my.save_character → my.reward 큐
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
        extra={
            **log_ctx,
            "character_id": reward["character_id"],
            "dispatched": dispatched,
        },
    )
