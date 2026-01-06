"""Answer Task - Pipeline Stage 3.

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
    get_answer_step,
    get_checkpointing_step_runner,
)

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    name="scan.answer",
    queue="scan.answer",
    max_retries=2,
    soft_time_limit=60,
    time_limit=90,
    default_retry_delay=1,
)
def answer_task(
    self: Task,
    prev_result: dict[str, Any],
) -> dict[str, Any]:
    """답변 생성 태스크 (Stage 3).

    Clean Architecture: Step + Port/Adapter 패턴.

    Args:
        prev_result: Rule 스테이지 결과

    Returns:
        다음 스테이지로 전달할 컨텍스트
    """
    # Context 복원
    ctx = ClassifyContext.from_dict(prev_result)

    log_ctx = {
        "task_id": ctx.task_id,
        "user_id": ctx.user_id,
        "celery_task_id": self.request.id,
        "stage": "answer",
    }
    logger.info("Answer task started", extra=log_ctx)

    try:
        # Step + Runner 조립 (DI) - Context에서 model 가져옴, 체크포인팅 적용
        step = get_answer_step(ctx.llm_model)
        runner = get_checkpointing_step_runner()

        # Step 실행 (이벤트 발행 + 체크포인트 저장)
        ctx = runner.run_step(step, "answer", ctx)

    except Exception as exc:
        logger.error(
            "Answer generation failed",
            extra={**log_ctx, "error": str(exc)},
            exc_info=True,
        )
        # Exponential backoff: 1s, 2s
        countdown = 2**self.request.retries
        raise self.retry(exc=exc, countdown=countdown)

    logger.info(
        "Answer task completed",
        extra={
            **log_ctx,
            "elapsed_ms": ctx.latencies.get("duration_answer_ms"),
            "has_disposal_rules": ctx.disposal_rules is not None,
        },
    )

    # 다음 Task로 전달
    return ctx.to_dict()
