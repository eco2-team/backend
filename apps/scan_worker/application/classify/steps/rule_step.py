"""Rule Step - 배출 규정 검색 단계.

Stage 2: 분류 결과에 맞는 배출 규정 검색 (Lite RAG).
RetrieverPort만 의존.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from scan_worker.application.classify.ports.retriever import RetrieverPort
from scan_worker.application.common.step_interface import Step

if TYPE_CHECKING:
    from scan_worker.application.classify.dto.classify_context import (
        ClassifyContext,
    )

logger = logging.getLogger(__name__)


class RuleStep(Step):
    """규정 검색 Step - RetrieverPort만 의존.

    분류 결과에 맞는 배출 규정을 검색하여 Context에 저장.
    progress: 25 → 50
    """

    def __init__(self, retriever: RetrieverPort):
        """초기화.

        Args:
            retriever: 규정 검색 Port
        """
        self._retriever = retriever

    def run(self, ctx: "ClassifyContext") -> "ClassifyContext":
        """Step 실행.

        Args:
            ctx: 입력 Context (classification 필드 필요)

        Returns:
            업데이트된 Context (disposal_rules 필드 채워짐)
        """
        start = time.perf_counter()

        logger.info(
            "RuleStep started",
            extra={"task_id": ctx.task_id},
        )

        # 분류 결과 확인
        if not ctx.classification:
            logger.warning(
                "RuleStep skipped - no classification",
                extra={"task_id": ctx.task_id},
            )
            ctx.progress = 50
            return ctx

        # 배출 규정 검색 (Port 통해 추상화)
        disposal_rules = self._retriever.get_disposal_rules(ctx.classification)

        elapsed = (time.perf_counter() - start) * 1000

        # Context 업데이트
        ctx.disposal_rules = disposal_rules
        ctx.latencies["duration_rule_ms"] = elapsed
        ctx.progress = 50

        if not disposal_rules:
            logger.warning(
                "RuleStep completed - no rules found",
                extra={"task_id": ctx.task_id, "elapsed_ms": elapsed},
            )
        else:
            logger.info(
                "RuleStep completed",
                extra={
                    "task_id": ctx.task_id,
                    "elapsed_ms": elapsed,
                    "rules_found": True,
                },
            )

        return ctx
