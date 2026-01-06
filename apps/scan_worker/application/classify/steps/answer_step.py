"""Answer Step - 자연어 답변 생성 단계.

Stage 3: 분류 결과 + 배출 규정 → 자연어 답변 생성.
LLMPort와 PromptRepositoryPort만 의존.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from scan_worker.application.classify.ports.llm_model import LLMPort
from scan_worker.application.classify.ports.prompt_repository import (
    PromptRepositoryPort,
)
from scan_worker.application.common.step_interface import Step

if TYPE_CHECKING:
    from scan_worker.application.classify.dto.classify_context import (
        ClassifyContext,
    )

logger = logging.getLogger(__name__)


class AnswerStep(Step):
    """답변 생성 Step - LLMPort만 의존.

    분류 결과와 배출 규정을 기반으로 자연어 답변 생성.
    progress: 50 → 75
    """

    def __init__(
        self,
        llm: LLMPort,
        prompt_repository: PromptRepositoryPort,
    ):
        """초기화.

        Args:
            llm: LLM 모델 Port
            prompt_repository: 프롬프트 리포지토리 Port
        """
        self._llm = llm
        self._prompts = prompt_repository

    def run(self, ctx: "ClassifyContext") -> "ClassifyContext":
        """Step 실행.

        Args:
            ctx: 입력 Context (classification, disposal_rules 필드 필요)

        Returns:
            업데이트된 Context (final_answer 필드 채워짐)
        """
        start = time.perf_counter()

        logger.info(
            "AnswerStep started",
            extra={"task_id": ctx.task_id},
        )

        # 배출 규정이 없으면 기본 답변 생성
        if not ctx.disposal_rules:
            ctx.final_answer = {
                "disposal_steps": {},
                "insufficiencies": ["배출 규정 매칭 실패"],
                "user_answer": "죄송합니다. 해당 폐기물에 대한 배출 규정을 찾지 못했습니다.",
            }
            elapsed = (time.perf_counter() - start) * 1000
            ctx.latencies["duration_answer_ms"] = elapsed
            ctx.progress = 75

            logger.warning(
                "AnswerStep completed - fallback answer",
                extra={"task_id": ctx.task_id, "elapsed_ms": elapsed},
            )
            return ctx

        # 시스템 프롬프트 로딩
        try:
            system_prompt = self._prompts.get_prompt("answer_generation_prompt")
        except FileNotFoundError:
            system_prompt = "당신은 폐기물 분리배출 전문가입니다."

        # 사용자 입력 결정
        user_input = ctx.user_input or "이 폐기물을 어떻게 분리배출해야 하나요?"

        # LLM 답변 생성 (Port 통해 추상화)
        final_answer = self._llm.generate_answer(
            classification=ctx.classification,
            disposal_rules=ctx.disposal_rules,
            user_input=user_input,
            system_prompt=system_prompt,
        )

        elapsed = (time.perf_counter() - start) * 1000

        # Context 업데이트
        ctx.final_answer = final_answer
        ctx.latencies["duration_answer_ms"] = elapsed
        ctx.progress = 75

        # 총 소요시간 계산
        ctx.latencies["duration_total_ms"] = (
            ctx.latencies.get("duration_vision_ms", 0)
            + ctx.latencies.get("duration_rule_ms", 0)
            + elapsed
        )

        logger.info(
            "AnswerStep completed",
            extra={
                "task_id": ctx.task_id,
                "elapsed_ms": elapsed,
                "has_insufficiencies": bool(final_answer.get("insufficiencies")),
            },
        )

        return ctx
