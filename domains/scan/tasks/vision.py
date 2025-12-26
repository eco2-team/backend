"""
Vision Classification Celery Task

GPT Vision을 사용한 이미지 분류 (Pipeline Step 1)

Note:
    gevent pool: 동기 함수 호출 시 자동으로 I/O가 greenlet 전환됨.
    asyncio 사용 시 event loop 충돌 발생하므로 동기 클라이언트 사용.
"""

from __future__ import annotations

import json
import logging
from time import perf_counter
from typing import Any

from domains._shared.celery.base_task import BaseTask
from domains._shared.events import get_sync_redis_client, publish_stage_event
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

    Note:
        gevent pool: 동기 호출이 자동으로 greenlet 전환됨.
        asyncio 대신 동기 클라이언트 사용 (event loop 충돌 방지).
    """
    # gevent pool: 동기 함수 사용 (asyncio event loop 충돌 방지)
    from domains._shared.waste_pipeline.vision import analyze_images

    log_ctx = {
        "task_id": task_id,
        "user_id": user_id,
        "celery_task_id": self.request.id,
        "stage": "vision",
    }
    logger.info("Vision task started", extra=log_ctx)

    # Redis Streams: 시작 이벤트 발행
    redis_client = get_sync_redis_client()
    publish_stage_event(redis_client, task_id, "vision", "started", progress=0)

    prompt_text = user_input or "이 폐기물을 어떻게 분리배출해야 하나요?"
    started = perf_counter()

    try:
        # gevent가 socket I/O를 자동으로 greenlet 전환
        result_payload = analyze_images(prompt_text, image_url, save_result=False)
        classification_result = _to_dict(result_payload)
    except Exception as exc:
        elapsed_ms = (perf_counter() - started) * 1000
        logger.error(
            "Vision analysis failed",
            extra={**log_ctx, "elapsed_ms": elapsed_ms, "error": str(exc)},
        )
        # Redis Streams: 실패 이벤트 발행
        publish_stage_event(
            redis_client,
            task_id,
            "vision",
            "failed",
            result={"error": str(exc)},
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

    # Redis Streams: 완료 이벤트 발행
    publish_stage_event(redis_client, task_id, "vision", "completed", progress=25)

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
