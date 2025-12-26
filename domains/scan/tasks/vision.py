"""
Vision Classification Celery Task

GPT Vision을 사용한 이미지 분류 (Pipeline Step 1)
"""

from __future__ import annotations

import json
import logging
from time import perf_counter
from typing import Any

from domains._shared.celery.base_task import BaseTask
from domains.scan.celery_app import celery_app

logger = logging.getLogger(__name__)


class VisionPipelineError(Exception):
    """Vision 파이프라인 처리 중 발생하는 오류."""


@celery_app.task(
    bind=True,
    base=BaseTask,
    name="scan.vision",
    queue="scan.vision",
    max_retries=2,
    soft_time_limit=60,
    time_limit=90,
)
def vision_task(
    self: BaseTask,
    task_id: str,
    user_id: str,
    image_url: str,
    user_input: str | None,
) -> dict[str, Any]:
    """Step 1: GPT Vision을 사용한 이미지 분류.

    Args:
        task_id: Unique task identifier
        user_id: User who initiated the scan
        image_url: URL of the waste image to classify
        user_input: Optional user question/prompt

    Returns:
        Dictionary containing task metadata and classification result
    """
    from domains._shared.waste_pipeline.vision import analyze_images

    log_ctx = {
        "task_id": task_id,
        "user_id": user_id,
        "celery_task_id": self.request.id,
        "stage": "vision",
    }
    logger.info("Vision task started", extra=log_ctx)

    prompt_text = user_input or "이 폐기물을 어떻게 분리배출해야 하나요?"
    started = perf_counter()

    try:
        result_payload = analyze_images(prompt_text, image_url)
        classification_result = _to_dict(result_payload)
    except Exception as exc:
        elapsed_ms = (perf_counter() - started) * 1000
        logger.error(
            "Vision analysis failed",
            extra={**log_ctx, "elapsed_ms": elapsed_ms, "error": str(exc)},
        )
        raise self.retry(exc=exc)

    elapsed_ms = (perf_counter() - started) * 1000
    logger.info(
        "Vision task completed",
        extra={
            **log_ctx,
            "elapsed_ms": elapsed_ms,
            "major_category": classification_result.get("classification", {}).get("major_category"),
        },
    )

    return {
        "task_id": task_id,
        "user_id": user_id,
        "image_url": image_url,
        "user_input": user_input,
        "classification_result": classification_result,
        "metadata": {
            "duration_vision_ms": elapsed_ms,
        },
    }


def _to_dict(payload: Any) -> dict[str, Any]:
    """분류 결과를 dictionary로 변환."""
    if isinstance(payload, dict):
        return payload
    if isinstance(payload, str):
        try:
            return json.loads(payload)
        except json.JSONDecodeError as exc:
            raise VisionPipelineError(f"분류 결과 파싱 실패: {exc}") from exc
    raise VisionPipelineError("분류 결과 형식이 올바르지 않습니다.")
