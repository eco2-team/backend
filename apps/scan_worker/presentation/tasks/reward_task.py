"""Reward Task - Pipeline Stage 4 (Final).

Clean Architecture 마이그레이션 완료.
domains 의존성 제거됨.
"""

from __future__ import annotations

import logging
from typing import Any

from celery import Task

from scan_worker.application.classify.dto.classify_context import ClassifyContext
from scan_worker.setup.celery import celery_app
from scan_worker.setup.dependencies import (
    get_checkpointing_step_runner,
    get_reward_step,
)

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    name="scan.reward",
    queue="scan.reward",
    max_retries=3,
    soft_time_limit=30,
    time_limit=60,
)
def reward_task(
    self: Task,
    prev_result: dict[str, Any],
) -> dict[str, Any]:
    """보상 처리 태스크 (Stage 4 - Final).

    Clean Architecture: Step + Port/Adapter 패턴.

    Flow:
        1. 조건 검증
        2. character.match 호출 (동기 대기) → 매칭 결과
        3. character.save_ownership, users.save_character 발행 (Fire & Forget)
        4. 결과 캐시 저장
        5. done 이벤트 발행

    Args:
        prev_result: Answer 스테이지 결과

    Returns:
        최종 파이프라인 결과
    """
    # Context 복원
    ctx = ClassifyContext.from_dict(prev_result)

    log_ctx = {
        "task_id": ctx.task_id,
        "user_id": ctx.user_id,
        "celery_task_id": self.request.id,
        "stage": "reward",
    }
    logger.info("Reward task started", extra=log_ctx)

    try:
        # Step + Runner 조립 (DI) - 체크포인팅 적용
        step = get_reward_step(celery_app)
        runner = get_checkpointing_step_runner()

        # Step 실행 (이벤트 발행 + 체크포인트 저장)
        ctx = runner.run_step(step, "reward", ctx)

    except Exception as exc:
        logger.error(
            "Reward processing failed",
            extra={**log_ctx, "error": str(exc)},
            exc_info=True,
        )
        raise self.retry(exc=exc)

    # 구조화된 로그
    logger.info(
        "scan_task_completed",
        extra={
            "event_type": "scan_completed",
            "task_id": ctx.task_id,
            "user_id": ctx.user_id,
            "category": (
                ctx.classification.get("classification", {}).get("major_category")
                if ctx.classification
                else None
            ),
            "duration_total_ms": ctx.latencies.get("duration_total_ms"),
            "duration_vision_ms": ctx.latencies.get("duration_vision_ms"),
            "duration_rule_ms": ctx.latencies.get("duration_rule_ms"),
            "duration_answer_ms": ctx.latencies.get("duration_answer_ms"),
            "has_disposal_rules": ctx.disposal_rules is not None,
            "has_reward": ctx.reward is not None,
            "matched_character": ctx.reward.get("name") if ctx.reward else None,
        },
    )

    # [Legacy] 커스텀 이벤트 발행 (Celery Events 방식)
    try:
        self.send_event(
            "task-result",
            result=ctx.to_dict(),
            task_id=ctx.task_id,
            root_id=ctx.task_id,
        )
        logger.debug("task_result_event_sent", extra={"task_id": ctx.task_id})
    except Exception as e:
        logger.warning(
            "task_result_event_failed",
            extra={"task_id": ctx.task_id, "error": str(e)},
        )

    return ctx.to_dict()
