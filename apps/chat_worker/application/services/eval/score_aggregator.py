"""Score Aggregator Service - 다층 평가 결과 통합.

L1 Code Grader + L2 LLM Grader 결과를 EvalResult로 통합.
Domain Service(EvalScoringService) 위임으로 순수 비즈니스 로직 유지.

Clean Architecture:
- Service: 이 파일 (Domain Service 위임, 얇은 오케스트레이션)
- Command: EvaluateResponseCommand에서 호출

참조: docs/plans/chat-eval-pipeline-plan.md Section 4.2
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from chat_worker.domain.enums.eval_grade import EvalGrade
from chat_worker.domain.services.eval_scoring import EvalScoringService

if TYPE_CHECKING:
    from chat_worker.application.dto.eval_result import EvalResult
    from chat_worker.application.services.eval.code_grader import CodeGraderResult
    from chat_worker.domain.value_objects.axis_score import AxisScore

logger = logging.getLogger(__name__)

# Intent별 가중치 매핑 (위험물 intent는 Safety 부스트)
_HAZARDOUS_INTENTS: frozenset[str] = frozenset({"waste", "bulk_waste"})


class ScoreAggregatorService:
    """다층 평가 결과 통합 Service.

    L1 Code Grader와 L2 LLM Grader의 결과를 합산하여
    최종 EvalResult를 생성합니다.

    외부 Port 의존 없음: Domain Service(EvalScoringService)에 위임.
    """

    def aggregate(
        self,
        code_result: CodeGraderResult,
        llm_scores: dict[str, AxisScore] | None,
        intent: str,
        model_version: str = "unknown",
        prompt_version: str = "unknown",
        eval_duration_ms: int = 0,
        eval_cost_usd: float | None = None,
        calibration_status: str | None = None,
    ) -> EvalResult:
        """다층 평가 결과 통합.

        LLM 점수가 있으면 BARS 5축 기반 연속 점수 산출.
        없으면 Code Grader만으로 degraded mode 평가.

        Args:
            code_result: L1 Code Grader 결과
            llm_scores: L2 LLM Grader 축별 점수 (None이면 code-only)
            intent: 분류된 Intent
            model_version: 평가에 사용된 모델 ID
            prompt_version: 루브릭 git SHA
            eval_duration_ms: 평가 소요 시간 (밀리초)
            eval_cost_usd: 평가 비용 (USD)
            calibration_status: L3 Calibration 상태 ("STABLE" | "DRIFTING" | None)

        Returns:
            EvalResult: 통합된 평가 결과
        """
        # lazy import: EvalResult → ScoreAggregatorService 양방향 참조 방지
        # (EvalResult.code_only()가 EvalGrade를 사용하고, aggregate()가 EvalResult를 반환)
        from chat_worker.application.dto.eval_result import EvalResult

        # LLM 점수 없으면 Code-only degraded mode
        if not llm_scores:
            return self._aggregate_code_only(
                code_result=code_result,
                model_version=model_version,
                prompt_version=prompt_version,
                eval_duration_ms=eval_duration_ms,
            )

        # Intent 기반 가중치 선택
        weights = (
            EvalScoringService.HAZARDOUS_WEIGHTS
            if intent in _HAZARDOUS_INTENTS
            else EvalScoringService.DEFAULT_WEIGHTS
        )

        # Domain Service 위임: BARS 5축 → ContinuousScore
        continuous = EvalScoringService.compute_continuous_score(
            axis_scores=llm_scores,
            weights=weights,
        )

        # 등급 산출
        grade = EvalGrade.from_continuous_score(continuous.value)

        # 축별 점수를 dict로 변환
        axis_scores_dict: dict[str, dict[str, Any]] = {
            axis: score.to_dict() for axis, score in llm_scores.items()
        }

        result = EvalResult(
            continuous_score=continuous.value,
            axis_scores=axis_scores_dict,
            grade=grade.value,
            information_loss=continuous.information_loss,
            grade_confidence=continuous.grade_confidence,
            code_grader_result=code_result.to_dict(),
            llm_grader_result=axis_scores_dict,
            calibration_status=calibration_status,
            model_version=model_version,
            prompt_version=prompt_version,
            eval_duration_ms=eval_duration_ms,
            eval_cost_usd=eval_cost_usd,
            metadata={
                "mode": "full",
                "intent_weights": "hazardous" if intent in _HAZARDOUS_INTENTS else "default",
            },
        )

        logger.debug(
            "Score aggregation completed (full mode)",
            extra={
                "intent": intent,
                "continuous_score": continuous.value,
                "grade": grade.value,
                "axes": list(llm_scores.keys()),
            },
        )

        return result

    def _aggregate_code_only(
        self,
        code_result: CodeGraderResult,
        model_version: str,
        prompt_version: str,
        eval_duration_ms: int,
    ) -> EvalResult:
        """Code Grader만으로 degraded mode 결과 생성.

        Args:
            code_result: L1 Code Grader 결과
            model_version: 모델 버전
            prompt_version: 프롬프트 버전
            eval_duration_ms: 평가 소요 시간

        Returns:
            EvalResult (code_only mode)
        """
        from chat_worker.application.dto.eval_result import EvalResult

        continuous_score = code_result.overall_score * 100
        grade = EvalGrade.from_continuous_score(continuous_score)

        result = EvalResult.code_only(
            code_result_dict=code_result.to_dict(),
            continuous_score=round(continuous_score, 2),
            grade=grade.value,
            model_version=model_version,
            prompt_version=prompt_version,
            eval_duration_ms=eval_duration_ms,
        )

        logger.debug(
            "Score aggregation completed (code-only degraded mode)",
            extra={
                "continuous_score": continuous_score,
                "grade": grade.value,
                "overall_code_score": code_result.overall_score,
            },
        )

        return result


__all__ = ["ScoreAggregatorService"]
