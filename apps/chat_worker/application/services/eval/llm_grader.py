"""LLM Grader Service - L2 LLM 기반 BARS 5축 평가.

Swiss Cheese Layer 2: BARS Rubric 기반 LLM 채점.
Self-Consistency 전략으로 경계 구간(2, 4) 안정성 확보.

Clean Architecture:
- Service: 이 파일 (BARSEvaluator Port 의존)
- Node: eval subgraph의 llm_grader 노드에서 호출
- Command: EvaluateResponseCommand에서 오케스트레이션

참조: docs/plans/chat-eval-pipeline-plan.md Section 3.2
"""

from __future__ import annotations

import asyncio
import logging
import statistics
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from chat_worker.application.dto.eval_config import EvalConfig
    from chat_worker.application.ports.eval.bars_evaluator import BARSEvaluator
    from chat_worker.domain.value_objects.axis_score import AxisScore

logger = logging.getLogger(__name__)

# Self-Consistency 경계 구간 (BARS 1-5에서 2, 4는 등급 경계에 가까움)
_BOUNDARY_SCORES: frozenset[int] = frozenset({2, 4})

# 모드별 타임아웃 (초)
_MODE_TIMEOUT: dict[str, float] = {
    "sync": 5.0,
    "async": 30.0,
    "shadow": 60.0,
}


class LLMGraderService:
    """L2 LLM-Based BARS Grader.

    BARS 5-Axis Rubric을 기반으로 LLM을 호출하여 채점.
    경계 구간(score 2, 4)에 대해 Self-Consistency 전략 적용.

    Port 의존: BARSEvaluator (Infrastructure에서 주입).
    """

    def __init__(
        self,
        bars_evaluator: BARSEvaluator,
        eval_config: EvalConfig,
    ) -> None:
        """Service 초기화.

        Args:
            bars_evaluator: BARS 5축 평가 Port
            eval_config: Eval Pipeline 설정 (self-consistency runs, mode 등)
        """
        self._bars_evaluator = bars_evaluator
        self._eval_config = eval_config

    async def evaluate(
        self,
        query: str,
        context: str,
        answer: str,
        intent: str,
    ) -> dict[str, AxisScore]:
        """BARS 5축 LLM 평가 실행.

        Self-Consistency: 경계 구간(score 2, 4) 축에 대해
        추가 N회 재평가 후 중앙값 채택으로 안정성 확보.

        Args:
            query: 사용자 질문
            context: RAG 컨텍스트
            answer: 생성된 답변
            intent: 분류된 Intent

        Returns:
            축 이름 -> AxisScore 매핑 (실패 시 빈 dict)
        """
        timeout = _MODE_TIMEOUT.get(self._eval_config.eval_mode, 30.0)

        try:
            result = await asyncio.wait_for(
                self._evaluate_with_self_consistency(query, context, answer),
                timeout=timeout,
            )
            logger.debug(
                "LLM grader evaluation completed",
                extra={
                    "intent": intent,
                    "axes_evaluated": list(result.keys()),
                    "timeout": timeout,
                },
            )
            return result

        except asyncio.TimeoutError:
            logger.warning(
                "LLM grader evaluation timed out, returning empty (graceful degradation)",
                extra={"intent": intent, "timeout_seconds": timeout},
            )
            return {}

        except Exception:
            logger.warning(
                "LLM grader evaluation failed, returning empty (graceful degradation)",
                extra={"intent": intent},
                exc_info=True,
            )
            return {}

    async def _evaluate_with_self_consistency(
        self,
        query: str,
        context: str,
        answer: str,
    ) -> dict[str, AxisScore]:
        """Self-Consistency 전략 포함 평가.

        1. 전체 5축 일괄 평가
        2. 경계 구간(2, 4) 축 식별
        3. 해당 축만 N회 추가 평가 → 중앙값 채택

        Args:
            query: 사용자 질문
            context: RAG 컨텍스트
            answer: 생성된 답변

        Returns:
            축 이름 -> AxisScore 매핑
        """
        # 1. 전체 5축 일괄 평가 (단일 프롬프트, 비용 절감)
        axis_scores = await self._bars_evaluator.evaluate_all_axes(
            query=query,
            context=context,
            answer=answer,
        )

        # 2. 경계 구간 축 식별
        boundary_axes = [
            axis for axis, score in axis_scores.items() if score.score in _BOUNDARY_SCORES
        ]

        if not boundary_axes:
            return axis_scores

        # 3. Self-Consistency: 경계 축만 추가 N회 평가
        sc_runs = self._eval_config.eval_self_consistency_runs
        logger.debug(
            "Self-Consistency triggered for boundary axes",
            extra={"boundary_axes": boundary_axes, "runs": sc_runs},
        )

        for axis in boundary_axes:
            additional_scores: list[int] = [axis_scores[axis].score]
            all_axis_scores: list[AxisScore] = [axis_scores[axis]]

            for _ in range(sc_runs):
                re_score = await self._bars_evaluator.evaluate_axis(
                    axis=axis,
                    query=query,
                    context=context,
                    answer=answer,
                )
                additional_scores.append(re_score.score)
                all_axis_scores.append(re_score)

            # 중앙값 채택
            median_score = int(statistics.median(additional_scores))

            # 원래 점수와 동일하면 변경 불필요
            if median_score == axis_scores[axis].score:
                continue

            # 수집된 AxisScore 중 median에 가장 가까운 것을 선택 (추가 LLM 호출 없음)
            # all_axis_scores[0]은 원본, [1:]은 재평가 결과
            # median과 일치하는 것이 없으면 원본 유지 (보수적 전략)
            best_match = axis_scores[axis]  # fallback: 원본
            for collected_score in all_axis_scores:
                if collected_score.score == median_score:
                    best_match = collected_score
                    break

            axis_scores[axis] = best_match

            logger.debug(
                "Self-Consistency result",
                extra={
                    "axis": axis,
                    "original_score": additional_scores[0],
                    "median_score": median_score,
                    "adopted_score": best_match.score,
                    "all_scores": additional_scores,
                },
            )

        return axis_scores


__all__ = ["LLMGraderService"]
