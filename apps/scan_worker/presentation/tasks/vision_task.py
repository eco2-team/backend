"""Vision Task - Pipeline Stage 1.

Clean Architecture 마이그레이션 완료.
domains 의존성 제거됨.
"""

from __future__ import annotations

import logging
from typing import Any

from celery import Task

from scan_worker.setup.celery import celery_app
from scan_worker.setup.dependencies import (
    create_context,
    get_checkpointing_step_runner,
    get_vision_step,
)

logger = logging.getLogger(__name__)


class VisionPipelineError(Exception):
    """Vision 파이프라인 처리 중 발생하는 오류."""


@celery_app.task(
    bind=True,
    name="scan.vision",
    queue="scan.vision",
    max_retries=2,
    soft_time_limit=60,
    time_limit=90,
    default_retry_delay=1,
)
def vision_task(
    self: Task,
    task_id: str,
    user_id: str,
    image_url: str,
    user_input: str | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    """Vision 분석 태스크 (Stage 1).

    Clean Architecture: Step + Port/Adapter 패턴.

    Args:
        task_id: 작업 ID (UUID)
        user_id: 사용자 ID
        image_url: 이미지 URL
        user_input: 사용자 입력
        model: LLM 모델명 (None이면 기본값 사용)

    Returns:
        다음 스테이지로 전달할 컨텍스트
    """
    log_ctx = {
        "task_id": task_id,
        "user_id": user_id,
        "celery_task_id": self.request.id,
        "stage": "vision",
        "model": model,
    }
    logger.info("Vision task started", extra=log_ctx)

    # Context 생성
    ctx = create_context(
        task_id=task_id,
        user_id=user_id,
        image_url=image_url,
        user_input=user_input,
        model=model,
    )

    try:
        # Step + Runner 조립 (DI) - 체크포인팅 적용
        step = get_vision_step(model)
        runner = get_checkpointing_step_runner()

        # Step 실행 (이벤트 발행 + 체크포인트 저장)
        ctx = runner.run_step(step, "vision", ctx)

    except Exception as exc:
        logger.error(
            "Vision analysis failed",
            extra={**log_ctx, "error": str(exc)},
            exc_info=True,
        )
        # Exponential backoff: 1s, 2s
        countdown = 2**self.request.retries
        raise self.retry(exc=exc, countdown=countdown)

    logger.info(
        "Vision task completed",
        extra={
            **log_ctx,
            "elapsed_ms": ctx.latencies.get("duration_vision_ms"),
            "major_category": (
                ctx.classification.get("classification", {}).get("major_category")
                if ctx.classification
                else None
            ),
        },
    )

    # 다음 Task로 전달
    return ctx.to_dict()
