"""
Rule-based Retrieval Celery Task

RAG 기반 배출 규정 검색 (Pipeline Step 2)
"""

from __future__ import annotations

import logging
from time import perf_counter
from typing import Any

from domains._shared.celery.base_task import BaseTask
from domains.scan.celery_app import celery_app

logger = logging.getLogger(__name__)


class RulePipelineError(Exception):
    """Rule 검색 중 발생하는 오류."""


@celery_app.task(
    bind=True,
    base=BaseTask,
    name="scan.rule",
    queue="scan.rule",
    max_retries=3,
    soft_time_limit=30,
    time_limit=60,
)
def rule_task(
    self: BaseTask,
    prev_result: dict[str, Any],
) -> dict[str, Any]:
    """Step 2: Rule-based Retrieval (RAG).

    분류 결과를 기반으로 배출 규정을 검색합니다.

    Args:
        prev_result: vision_task의 결과
            - task_id: str
            - user_id: str
            - image_url: str
            - user_input: str | None
            - classification_result: dict
            - metadata: dict

    Returns:
        prev_result에 disposal_rules와 metadata 추가
    """
    from domains._shared.waste_pipeline.rag import get_disposal_rules

    task_id = prev_result.get("task_id")
    user_id = prev_result.get("user_id")
    classification_result = prev_result.get("classification_result", {})

    log_ctx = {
        "task_id": task_id,
        "user_id": user_id,
        "celery_task_id": self.request.id,
        "stage": "rule",
    }
    logger.info("Rule task started", extra=log_ctx)

    started = perf_counter()

    try:
        disposal_rules = get_disposal_rules(classification_result)
        if not disposal_rules:
            raise RulePipelineError("매칭되는 배출 규정을 찾지 못했습니다.")
    except RulePipelineError:
        # 규정을 찾지 못한 경우 재시도하지 않고 빈 결과로 진행
        elapsed_ms = (perf_counter() - started) * 1000
        logger.warning(
            "No disposal rules found",
            extra={**log_ctx, "elapsed_ms": elapsed_ms},
        )
        disposal_rules = None
    except Exception as exc:
        elapsed_ms = (perf_counter() - started) * 1000
        logger.error(
            "Rule retrieval failed",
            extra={**log_ctx, "elapsed_ms": elapsed_ms, "error": str(exc)},
        )
        raise self.retry(exc=exc)

    elapsed_ms = (perf_counter() - started) * 1000
    logger.info(
        "Rule task completed",
        extra={
            **log_ctx,
            "elapsed_ms": elapsed_ms,
            "rules_found": disposal_rules is not None,
        },
    )

    # 메타데이터 업데이트
    metadata = prev_result.get("metadata", {})
    metadata["duration_rule_ms"] = elapsed_ms

    return {
        **prev_result,
        "disposal_rules": disposal_rules,
        "metadata": metadata,
    }
