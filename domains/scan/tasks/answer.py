"""
Answer Generation Celery Task

GPT를 사용한 최종 답변 생성 (Pipeline Step 3)
Webhook 전송은 reward_task에서 수행
"""

from __future__ import annotations

import logging
from time import perf_counter
from typing import Any

from domains._shared.celery.base_task import BaseTask
from domains.scan.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    base=BaseTask,
    name="scan.answer",
    queue="scan.answer",
    max_retries=2,
    soft_time_limit=60,
    time_limit=90,
)
def answer_task(
    self: BaseTask,
    prev_result: dict[str, Any],
) -> dict[str, Any]:
    """Step 3: Answer Generation.

    분류 결과와 배출 규정을 기반으로 최종 답변을 생성합니다.
    Webhook 전송은 reward_task에서 수행됩니다.

    Args:
        prev_result: rule_task의 결과
            - task_id: str
            - user_id: str
            - image_url: str
            - user_input: str | None
            - classification_result: dict
            - disposal_rules: dict | None
            - metadata: dict

    Returns:
        최종 파이프라인 결과 (reward_task로 전달)
    """
    from domains._shared.celery.async_support import run_async
    from domains._shared.waste_pipeline.answer import generate_answer_async

    task_id = prev_result.get("task_id")
    user_id = prev_result.get("user_id")
    classification_result = prev_result.get("classification_result", {})
    disposal_rules = prev_result.get("disposal_rules")

    log_ctx = {
        "task_id": task_id,
        "user_id": user_id,
        "celery_task_id": self.request.id,
        "stage": "answer",
    }
    logger.info("Answer task started (async)", extra=log_ctx)

    started = perf_counter()

    # 배출 규정이 없으면 기본 답변 생성
    if not disposal_rules:
        final_answer = {
            "answer": "죄송합니다. 해당 폐기물에 대한 배출 규정을 찾지 못했습니다.",
            "insufficiencies": ["배출 규정 매칭 실패"],
        }
        elapsed_ms = (perf_counter() - started) * 1000
    else:
        try:
            # AsyncOpenAI 사용 (공유 event loop에서 실행)
            final_answer = run_async(generate_answer_async(classification_result, disposal_rules))
        except Exception as exc:
            elapsed_ms = (perf_counter() - started) * 1000
            logger.error(
                "Answer generation failed",
                extra={**log_ctx, "elapsed_ms": elapsed_ms, "error": str(exc)},
            )
            raise self.retry(exc=exc)

        elapsed_ms = (perf_counter() - started) * 1000

    logger.info(
        "Answer task completed",
        extra={**log_ctx, "elapsed_ms": elapsed_ms},
    )

    # 메타데이터 업데이트
    metadata = prev_result.get("metadata", {})
    metadata["duration_answer_ms"] = elapsed_ms
    metadata["duration_total_ms"] = (
        metadata.get("duration_vision_ms", 0) + metadata.get("duration_rule_ms", 0) + elapsed_ms
    )

    # 분류 결과에서 카테고리 추출
    classification = classification_result.get("classification", {})
    category = classification.get("major_category")

    # 최종 결과 구성
    result = {
        "task_id": task_id,
        "user_id": user_id,
        "status": "completed",
        "category": category,
        "classification_result": classification_result,
        "disposal_rules": disposal_rules,
        "final_answer": final_answer,
        "metadata": metadata,
    }

    # 구조화된 로그 출력 (EFK 파이프라인으로 수집)
    logger.info(
        "scan_answer_generated",
        extra={
            "event_type": "scan_answer_generated",
            "task_id": task_id,
            "user_id": user_id,
            "category": category,
            "duration_answer_ms": metadata.get("duration_answer_ms"),
            "has_disposal_rules": disposal_rules is not None,
            "has_insufficiencies": bool(final_answer.get("insufficiencies")),
        },
    )

    # reward_task로 전달
    return result
