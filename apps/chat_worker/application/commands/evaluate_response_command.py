"""Evaluate Response Command - 3-Tier 응답 품질 평가 오케스트레이터.

Swiss Cheese 3-Tier Grader 파이프라인을 오케스트레이션하는 UseCase.

L1: Code Grader (결정적, < 50ms)
L2: LLM Grader (BARS 5축, Self-Consistency)
L3: Calibration Monitor (CUSUM Drift 감지)

Clean Architecture:
- Command(UseCase): 이 파일 - 정책/흐름 담당, Port 조립
- Service: CodeGraderService, LLMGraderService, ScoreAggregatorService, CalibrationMonitorService
- Port: BARSEvaluator, EvalResultCommandGateway
- Node(Adapter): eval_node.py - LangGraph 어댑터

참조: docs/plans/chat-eval-pipeline-plan.md Section 2, 4
"""

from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from chat_worker.application.dto.eval_config import EvalConfig
    from chat_worker.application.dto.eval_result import EvalResult
    from chat_worker.application.ports.eval.eval_result_command_gateway import (
        EvalResultCommandGateway,
    )
    from chat_worker.application.ports.eval.eval_result_query_gateway import (
        EvalResultQueryGateway,
    )
    from chat_worker.application.services.eval.calibration_monitor import (
        CalibrationMonitorService,
    )
    from chat_worker.application.services.eval.code_grader import (
        CodeGraderResult,
        CodeGraderService,
    )
    from chat_worker.application.services.eval.llm_grader import LLMGraderService
    from chat_worker.application.services.eval.score_aggregator import (
        ScoreAggregatorService,
    )

logger = logging.getLogger(__name__)


# ── Input / Output DTO ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class EvaluateResponseInput:
    """Command 입력 DTO.

    Attributes:
        query: 사용자 질문
        intent: 분류된 Intent
        answer: 생성된 답변
        rag_context: RAG 컨텍스트
        feedback_result: Feedback 평가 결과 (dict, 참고용)
        job_id: 작업 ID (추적용)
    """

    query: str
    intent: str
    answer: str
    rag_context: str
    feedback_result: dict[str, Any] | None
    job_id: str


@dataclass
class EvaluateResponseOutput:
    """Command 출력 DTO.

    Attributes:
        eval_result: 통합 평가 결과
        calibration_status: Calibration 상태 (L3)
        needs_regeneration: 재생성 필요 여부 (C등급)
        improvement_hints: 개선 힌트 목록
    """

    eval_result: EvalResult
    calibration_status: str | None = None
    needs_regeneration: bool = False
    improvement_hints: list[str] = field(default_factory=list)


# ── Command ───────────────────────────────────────────────────────────────────


class EvaluateResponseCommand:
    """3-Tier 응답 품질 평가 Command (UseCase).

    Swiss Cheese 모델 기반 3계층 평가 오케스트레이션.

    정책/흐름:
    1. L1: Code Grader (항상 실행, 결정적)
    2. L2: LLM Grader (조건부, BARS 5축)
    3. Aggregate: 다층 결과 통합 → EvalResult
    4. L3: Calibration Monitor (주기적, CUSUM)
    5. Save: 결과 저장 (Gateway 있을 때)
    6. 재생성 판단: C등급이면 needs_regeneration=True

    Port 주입:
    - eval_result_gw: 결과 저장 (선택적)
    """

    def __init__(
        self,
        code_grader: CodeGraderService,
        llm_grader: LLMGraderService | None,
        score_aggregator: ScoreAggregatorService,
        calibration_monitor: CalibrationMonitorService | None,
        eval_result_gw: EvalResultCommandGateway | None,
        eval_config: EvalConfig,
        eval_result_query_gw: EvalResultQueryGateway | None = None,
    ) -> None:
        """Command 초기화.

        Args:
            code_grader: L1 Code Grader Service
            llm_grader: L2 LLM Grader Service (None이면 L1만 실행)
            score_aggregator: 다층 결과 통합 Service
            calibration_monitor: L3 Calibration Monitor Service (선택)
            eval_result_gw: 평가 결과 저장 Gateway (선택)
            eval_config: Eval Pipeline 설정
            eval_result_query_gw: 평가 결과 조회 Gateway (비용 추적용, 선택)
        """
        self._code_grader = code_grader
        self._llm_grader = llm_grader
        self._score_aggregator = score_aggregator
        self._calibration_monitor = calibration_monitor
        self._eval_result_gw = eval_result_gw
        self._eval_config = eval_config
        self._eval_result_query_gw = eval_result_query_gw
        self._request_counter: int = 0

    async def execute(
        self,
        input_dto: EvaluateResponseInput,
    ) -> EvaluateResponseOutput:
        """Command 실행: 3-Tier 평가 파이프라인.

        Args:
            input_dto: 입력 DTO

        Returns:
            출력 DTO (eval_result, calibration_status, needs_regeneration, improvement_hints)
        """
        # 샘플링 게이트: eval_sample_rate 미만이면 평가 건너뛰기
        if random.random() > self._eval_config.eval_sample_rate:
            from chat_worker.application.dto.eval_result import EvalResult

            skipped = EvalResult.failed("sampled_out")
            return EvaluateResponseOutput(eval_result=skipped)

        self._request_counter += 1
        start_time = time.monotonic()
        hints: list[str] = []

        code_result = self._run_code_grader(input_dto, hints)
        llm_scores = await self._run_llm_grader(input_dto, hints)

        elapsed_ms = int((time.monotonic() - start_time) * 1000)
        eval_result = self._score_aggregator.aggregate(
            code_result=code_result,
            llm_scores=llm_scores,
            intent=input_dto.intent,
            model_version=self._eval_config.eval_model,
            prompt_version="unknown",
            eval_duration_ms=elapsed_ms,
        )

        calibration_status = await self._run_calibration(input_dto.job_id)
        await self._save_result(eval_result, input_dto.job_id)

        needs_regeneration = (
            eval_result.grade == "C" and self._eval_config.eval_regeneration_enabled
        )

        return EvaluateResponseOutput(
            eval_result=eval_result,
            calibration_status=calibration_status,
            needs_regeneration=needs_regeneration,
            improvement_hints=hints,
        )

    def _run_code_grader(
        self,
        input_dto: EvaluateResponseInput,
        hints: list[str],
    ) -> "CodeGraderResult":
        """L1 Code Grader 실행 및 힌트 수집."""
        code_result = self._code_grader.evaluate(
            answer=input_dto.answer,
            intent=input_dto.intent,
            query=input_dto.query,
        )
        logger.info(
            "L1 Code Grader completed",
            extra={
                "job_id": input_dto.job_id,
                "overall_score": code_result.overall_score,
            },
        )
        for slice_name, passed in code_result.passed.items():
            if not passed:
                hints.append(f"[L1] {slice_name}: {code_result.details[slice_name]}")
        return code_result

    async def _run_llm_grader(
        self,
        input_dto: EvaluateResponseInput,
        hints: list[str],
    ) -> dict | None:
        """L2 LLM Grader 조건부 실행."""
        if not await self._should_run_llm_grader():
            return None

        llm_scores = await self._llm_grader.evaluate(  # type: ignore[union-attr]
            query=input_dto.query,
            context=input_dto.rag_context,
            answer=input_dto.answer,
            intent=input_dto.intent,
        )
        if not llm_scores:
            logger.warning("L2 returned empty (degraded)", extra={"job_id": input_dto.job_id})
            return None

        for axis, score in llm_scores.items():
            if score.score <= 2:
                hints.append(f"[L2] {axis}: score={score.score}, reason={score.reasoning}")
        return llm_scores

    async def _run_calibration(self, job_id: str) -> str | None:
        """L3 Calibration Monitor 주기적 실행 (non-blocking)."""
        if not self._should_run_calibration():
            return None
        try:
            drift_result = await self._calibration_monitor.check_drift()  # type: ignore[union-attr]
            return drift_result.get("status")
        except Exception:
            logger.warning("L3 Calibration failed", extra={"job_id": job_id}, exc_info=True)
            return None

    async def _save_result(self, eval_result: "EvalResult", job_id: str) -> None:
        """평가 결과 저장 (non-blocking)."""
        if self._eval_result_gw is None:
            return
        try:
            await self._eval_result_gw.save_result(eval_result)
        except Exception:
            logger.warning("Save eval result failed", extra={"job_id": job_id}, exc_info=True)

    async def _should_run_llm_grader(self) -> bool:
        """L2 LLM Grader 실행 여부 판단 (비용 가드레일 포함).

        Returns:
            LLM Grader 실행 가능 여부
        """
        if self._llm_grader is None or not self._eval_config.eval_llm_grader_enabled:
            return False

        # 일일 비용 가드레일: 예산 초과 시 L2 비활성화
        if self._eval_result_query_gw is not None:
            try:
                daily_cost = await self._eval_result_query_gw.get_daily_cost()
                if daily_cost >= self._eval_config.eval_cost_budget_daily_usd:
                    logger.warning(
                        "Daily eval budget exceeded, disabling L2 LLM Grader",
                        extra={
                            "daily_cost": daily_cost,
                            "budget": self._eval_config.eval_cost_budget_daily_usd,
                        },
                    )
                    return False
            except Exception:
                logger.debug("Cost check failed, proceeding with L2", exc_info=True)

        return True

    def _should_run_calibration(self) -> bool:
        """L3 Calibration Monitor 실행 여부 판단 (주기적 실행).

        eval_cusum_check_interval 마다 한 번씩 실행합니다.

        Returns:
            Calibration Monitor 실행 가능 여부
        """
        if self._calibration_monitor is None:
            return False
        interval = self._eval_config.eval_cusum_check_interval
        if interval <= 0:
            return False
        return self._request_counter % interval == 0


__all__ = [
    "EvaluateResponseCommand",
    "EvaluateResponseInput",
    "EvaluateResponseOutput",
]
