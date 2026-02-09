"""Eval Subgraph Factory.

LangGraph StateGraph 기반 Eval Pipeline 서브그래프 빌더.
Swiss Cheese 3-Tier Grader (Code + LLM + Calibration)를
Send API로 병렬 실행합니다.

아키텍처:
```
eval_entry → route_to_graders (Send API)
                    │
          ┌─────────┼─────────┐
          ▼         ▼         ▼
     code_grader  llm_grader  calibration_check
          │         │         │
          ▼         ▼         ▼
            eval_aggregator
                    │
                    ▼
            eval_decision → END
```

Send API 패턴: dynamic_router.py 참조
Node factory 패턴: rag_node.py, feedback_node.py 참조

See: docs/plans/chat-eval-pipeline-plan.md §2.2, B.3
"""

from __future__ import annotations

import json
import logging
import time
from typing import TYPE_CHECKING, Annotated, Any, TypedDict

from langgraph.graph import END, StateGraph
from langgraph.types import Send

from chat_worker.application.dto.eval_config import EvalConfig
from chat_worker.application.dto.eval_result import EvalResult
from chat_worker.infrastructure.orchestration.langgraph.nodes.eval_node import (
    create_eval_entry_node,
)
from chat_worker.infrastructure.orchestration.langgraph.state import (
    priority_preemptive_reducer,
)

if TYPE_CHECKING:
    from langgraph.graph.state import CompiledStateGraph

    from chat_worker.application.services.eval.calibration_monitor import (
        CalibrationMonitorService,
    )
    from chat_worker.application.services.eval.code_grader import CodeGraderService
    from chat_worker.application.services.eval.llm_grader import LLMGraderService
    from chat_worker.application.services.eval.score_aggregator import (
        ScoreAggregatorService,
    )

logger = logging.getLogger(__name__)


# ============================================================
# EvalState TypedDict (독립 서브그래프 상태)
# ============================================================


class EvalState(TypedDict, total=False):
    """Eval Pipeline 서브그래프 상태.

    ChatState와 독립된 TypedDict.
    eval_entry 노드가 ChatState → EvalState 변환을 수행.

    See: docs/plans/chat-eval-pipeline-plan.md §2.3

    계층 구조:
    - Input: ChatState에서 주입 (eval_entry가 매핑)
    - Config: eval 실행 설정
    - Grader Outputs: 각 Grader 결과 (Annotated Reducer)
    - Aggregated Output: 최종 eval 결과
    - Internal: short-circuit 시그널
    """

    # ── Input (ChatState에서 주입) ──
    query: str
    intent: str
    answer: str
    rag_context: dict[str, Any] | None
    conversation_history: list[dict[str, Any]]
    feedback_result: dict[str, Any] | None  # 기존 FeedbackResult 시딩용

    # ── Config ──
    llm_grader_enabled: bool
    should_run_calibration: bool
    eval_retry_count: int  # 재생성 카운터

    # ── Grader Outputs (각 채널 분리, priority_preemptive_reducer) ──
    code_grader_result: Annotated[dict[str, Any] | None, priority_preemptive_reducer]
    llm_grader_result: Annotated[dict[str, Any] | None, priority_preemptive_reducer]
    calibration_result: Annotated[dict[str, Any] | None, priority_preemptive_reducer]

    # ── Aggregated Output (ChatState로 자동 전파되는 동명 키) ──
    eval_result: dict[str, Any] | None  # EvalResult.to_dict()
    eval_grade: str | None  # EvalGrade.value
    eval_continuous_score: float | None  # 0-100
    eval_needs_regeneration: bool
    eval_improvement_hints: list[str]  # 재생성 시 answer_node에 전달할 피드백

    # ── Internal ──
    _entry_failed: bool  # eval_entry 실패 시 short-circuit 시그널
    _prev_eval_score: float | None  # 이전 턴의 eval 점수


# ============================================================
# Route Functions
# ============================================================


def route_to_graders(state: dict[str, Any]) -> list[Send]:
    """Send API로 병렬 Grader 디스패치.

    기존 dynamic_router.py 패턴 준수.
    _entry_failed 시 grader를 건너뛰고 eval_aggregator로 직행.

    See: docs/plans/chat-eval-pipeline-plan.md §2.2, B.3

    Args:
        state: EvalState

    Returns:
        list[Send] - 병렬 실행할 Grader 노드들
    """
    # 에러 short-circuit: entry 실패 시 grader 건너뛰고 aggregator로 직행
    if state.get("_entry_failed"):
        logger.warning(
            "eval_entry failed, short-circuiting to eval_aggregator",
        )
        return [Send("eval_aggregator", state)]

    sends: list[Send] = [Send("code_grader", state)]

    if state.get("llm_grader_enabled", True):
        sends.append(Send("llm_grader", state))

    # Calibration은 N번째 요청마다 (비용 절감)
    if state.get("should_run_calibration", False):
        sends.append(Send("calibration_check", state))

    logger.debug(
        "route_to_graders: dispatching %d graders",
        len(sends),
    )

    return sends


MINIMUM_IMPROVEMENT_THRESHOLD: float = 5.0
"""재생성 품질 게이트: 재생성 후 연속 점수가 이전 대비 이 값 이상 개선되지 않으면 중단."""


def create_route_after_eval(eval_config: EvalConfig):
    """route_after_eval 클로저 팩토리.

    eval_config를 캡처하여 eval_regeneration_enabled를
    ChatState에 저장하지 않고도 접근 가능하게 합니다.

    See: docs/plans/chat-eval-pipeline-plan.md §2.4, A.9

    Args:
        eval_config: Eval Pipeline 설정

    Returns:
        route_after_eval 라우팅 함수
    """

    def route_after_eval(state: dict[str, Any]) -> str:
        """eval_decision 결과 기반 재생성 판단.

        eval_decision_node가 설정한 eval_needs_regeneration을 읽어 판단.
        MINIMUM_IMPROVEMENT_THRESHOLD 미달 시 재생성 중단.

        Args:
            state: ChatState (서브그래프 출력이 병합된 상태)

        Returns:
            "pass" (END) 또는 "regenerate" (answer 재실행)
        """
        needs_regen = state.get("eval_needs_regeneration", False)

        if not needs_regen:
            return "pass"

        # 재생성 후 품질 게이트: 개선 폭이 임계치 미만이면 중단
        prev_score = state.get("_prev_eval_score")
        curr_score = state.get("eval_continuous_score", 0.0)
        if prev_score is not None and (curr_score - prev_score) < MINIMUM_IMPROVEMENT_THRESHOLD:
            logger.info(
                "Regeneration skipped: insufficient improvement",
                extra={
                    "prev_score": prev_score,
                    "curr_score": curr_score,
                    "threshold": MINIMUM_IMPROVEMENT_THRESHOLD,
                },
            )
            return "pass"

        return "regenerate"

    return route_after_eval


# ============================================================
# Node Factory Functions (실제 서비스 연결)
# ============================================================


def _create_code_grader_node(code_grader: "CodeGraderService"):
    """L1 Code Grader 노드 생성.

    CodeGraderService.evaluate()를 호출하고
    priority_preemptive_reducer 형식으로 반환.

    Args:
        code_grader: L1 Code Grader Service
    """

    async def code_grader_node(state: dict[str, Any]) -> dict[str, Any]:
        try:
            result = code_grader.evaluate(
                answer=state.get("answer", ""),
                intent=state.get("intent", ""),
                query=state.get("query", ""),
            )
            passed_count = sum(1 for v in result.passed.values() if v)
            total_count = len(result.passed)
            logger.info(
                "code_grader completed",
                extra={
                    "overall_score": result.overall_score,
                    "passed": f"{passed_count}/{total_count}",
                },
            )
            return {
                "code_grader_result": {
                    **result.to_dict(),
                    "success": True,
                    "_priority": 1,
                    "_sequence": 0,
                },
            }
        except Exception as e:
            logger.warning("code_grader failed: %s", e, exc_info=True)
            return {
                "code_grader_result": {
                    "success": False,
                    "_priority": 1,
                    "_sequence": 0,
                    "error": str(e),
                    "scores": {},
                    "overall_score": 0.0,
                    "passed": {},
                    "details": {},
                },
            }

    return code_grader_node


def _create_llm_grader_node(llm_grader: "LLMGraderService"):
    """L2 LLM Grader 노드 생성.

    LLMGraderService.evaluate()를 호출하고
    축별 AxisScore를 직렬화하여 반환.

    Args:
        llm_grader: L2 LLM Grader Service
    """

    async def llm_grader_node(state: dict[str, Any]) -> dict[str, Any]:
        try:
            # RAG 컨텍스트를 문자열로 변환
            rag_context = state.get("rag_context")
            context_str = json.dumps(rag_context, ensure_ascii=False) if rag_context else ""

            axis_scores = await llm_grader.evaluate(
                query=state.get("query", ""),
                context=context_str,
                answer=state.get("answer", ""),
                intent=state.get("intent", ""),
            )

            if not axis_scores:
                logger.warning("llm_grader returned empty scores")
                return {
                    "llm_grader_result": {
                        "success": False,
                        "_priority": 2,
                        "_sequence": 0,
                        "axis_scores": {},
                    },
                }

            avg_score = sum(s.score for s in axis_scores.values()) / len(axis_scores)
            logger.info(
                "llm_grader completed",
                extra={
                    "axes_count": len(axis_scores),
                    "bars_avg": round(avg_score, 2),
                    "axis_summary": {a: s.score for a, s in axis_scores.items()},
                },
            )

            return {
                "llm_grader_result": {
                    "success": True,
                    "_priority": 2,
                    "_sequence": 0,
                    "axis_scores": {axis: score.to_dict() for axis, score in axis_scores.items()},
                },
            }
        except Exception as e:
            logger.warning("llm_grader failed: %s", e, exc_info=True)
            return {
                "llm_grader_result": {
                    "success": False,
                    "_priority": 2,
                    "_sequence": 0,
                    "axis_scores": {},
                    "error": str(e),
                },
            }

    return llm_grader_node


def _create_calibration_node(calibration_monitor: "CalibrationMonitorService"):
    """L3 Calibration Check 노드 생성.

    CalibrationMonitorService.check_drift()를 호출.

    Args:
        calibration_monitor: L3 Calibration Monitor Service
    """

    async def calibration_check_node(state: dict[str, Any]) -> dict[str, Any]:
        try:
            drift_result = await calibration_monitor.check_drift()
            return {
                "calibration_result": {
                    **drift_result,
                    "success": True,
                    "_priority": 3,
                    "_sequence": 0,
                },
            }
        except Exception as e:
            logger.warning("calibration_check failed: %s", e, exc_info=True)
            return {
                "calibration_result": {
                    "success": False,
                    "_priority": 3,
                    "_sequence": 0,
                    "status": "STABLE",
                    "error": str(e),
                },
            }

    return calibration_check_node


def _create_eval_aggregator_node(
    score_aggregator: "ScoreAggregatorService",
    eval_config: EvalConfig,
):
    """Eval Aggregator 노드 생성.

    L1 Code Grader + L2 LLM Grader 결과를 ScoreAggregatorService로 통합.

    See: docs/plans/chat-eval-pipeline-plan.md A.3

    Args:
        score_aggregator: 다층 결과 통합 Service
        eval_config: Eval Pipeline 설정
    """
    from chat_worker.application.services.eval.code_grader import CodeGraderResult
    from chat_worker.domain.value_objects.axis_score import AxisScore

    async def eval_aggregator_node(state: dict[str, Any]) -> dict[str, Any]:
        start = time.monotonic()

        # _entry_failed 시 degraded 결과 전파
        if state.get("_entry_failed"):
            return {
                "eval_result": state.get("eval_result", {"degraded": True}),
                "eval_grade": state.get("eval_grade", "B"),
                "eval_continuous_score": state.get("eval_continuous_score", 0.0),
                "eval_needs_regeneration": False,
                "eval_improvement_hints": [],
            }

        try:
            # L1 Code Grader 결과 복원
            code_raw = state.get("code_grader_result", {})
            code_result = CodeGraderResult(
                scores=code_raw.get("scores", {}),
                passed=code_raw.get("passed", {}),
                details=code_raw.get("details", {}),
                overall_score=code_raw.get("overall_score", 0.0),
            )

            # L2 LLM Grader 결과 복원 (선택적)
            llm_raw = state.get("llm_grader_result", {})
            llm_scores = None
            if llm_raw and llm_raw.get("success") and llm_raw.get("axis_scores"):
                llm_scores = {
                    axis: AxisScore.from_dict(score_data)
                    for axis, score_data in llm_raw["axis_scores"].items()
                }

            # Calibration 상태
            cal_raw = state.get("calibration_result", {})
            cal_status = cal_raw.get("status") if cal_raw else None

            elapsed_ms = int((time.monotonic() - start) * 1000)

            eval_result = score_aggregator.aggregate(
                code_result=code_result,
                llm_scores=llm_scores,
                intent=state.get("intent", ""),
                model_version=eval_config.eval_model,
                prompt_version="unknown",
                eval_duration_ms=elapsed_ms,
                calibration_status=cal_status,
            )

            # 개선 힌트 수집
            hints: list[str] = []
            for slice_name, passed in code_result.passed.items():
                if not passed:
                    hints.append(f"[L1] {slice_name}: {code_result.details[slice_name]}")
            if llm_scores:
                for axis, score in llm_scores.items():
                    if score.score <= 2:
                        hints.append(
                            f"[L2] {axis}: score={score.score}, " f"reason={score.reasoning}"
                        )

            logger.info(
                "eval_aggregator completed",
                extra={
                    "grade": eval_result.grade,
                    "continuous_score": eval_result.continuous_score,
                    "elapsed_ms": elapsed_ms,
                    "has_llm_scores": llm_scores is not None,
                    "hint_count": len(hints),
                },
            )

            return {
                "eval_result": eval_result.to_dict(),
                "eval_grade": eval_result.grade,
                "eval_continuous_score": eval_result.continuous_score,
                "eval_needs_regeneration": False,  # decision 노드에서 결정
                "eval_improvement_hints": hints,
                "_prev_eval_score": state.get("eval_continuous_score"),
            }

        except Exception as e:
            logger.warning("eval_aggregator failed: %s", e, exc_info=True)
            failed = EvalResult.failed(f"aggregator: {e}")
            return {
                "eval_result": failed.to_dict(),
                "eval_grade": failed.grade,
                "eval_continuous_score": failed.continuous_score,
                "eval_needs_regeneration": False,
                "eval_improvement_hints": [],
            }

    return eval_aggregator_node


def _create_eval_decision_node(eval_config: EvalConfig):
    """Eval Decision 노드 생성.

    재생성 여부 결정 + eval_retry_count 증가.

    Args:
        eval_config: Eval Pipeline 설정
    """

    async def eval_decision_node(state: dict[str, Any]) -> dict[str, Any]:
        grade = state.get("eval_grade", "A")
        retry_count = state.get("eval_retry_count", 0)

        needs_regen = grade == "C" and retry_count < 1 and eval_config.eval_regeneration_enabled

        logger.info(
            "eval_decision completed",
            extra={
                "grade": grade,
                "retry_count": retry_count,
                "needs_regeneration": needs_regen,
                "regeneration_enabled": eval_config.eval_regeneration_enabled,
            },
        )

        return {
            "eval_needs_regeneration": needs_regen,
            "eval_retry_count": retry_count + 1 if needs_regen else retry_count,
        }

    return eval_decision_node


# ============================================================
# Subgraph Builder
# ============================================================


def create_eval_subgraph(
    eval_config: EvalConfig,
    code_grader: "CodeGraderService | None" = None,
    llm_grader: "LLMGraderService | None" = None,
    score_aggregator: "ScoreAggregatorService | None" = None,
    calibration_monitor: "CalibrationMonitorService | None" = None,
    eval_counter: "Any | None" = None,
) -> "CompiledStateGraph":
    """Eval Pipeline 서브그래프 생성.

    Swiss Cheese 3-Tier Grader를 Send API로 병렬 실행하는
    LangGraph StateGraph를 구성합니다.

    서비스가 주입되지 않으면(None) 해당 노드는 passthrough 동작.

    See: docs/plans/chat-eval-pipeline-plan.md §2.2, B.3

    Args:
        eval_config: Eval Pipeline 설정
        code_grader: L1 Code Grader 서비스
        llm_grader: L2 LLM Grader 서비스
        score_aggregator: 다층 결과 통합 서비스
        calibration_monitor: L3 Calibration Monitor 서비스
        eval_counter: RedisEvalCounter (None이면 stopgap fallback)

    Returns:
        컴파일된 Eval 서브그래프
    """
    eval_graph = StateGraph(EvalState)

    # Entry 노드: ChatState → EvalState 변환
    eval_entry = create_eval_entry_node(eval_config, eval_counter=eval_counter)
    eval_graph.add_node("eval_entry", eval_entry)

    # L1 Code Grader 노드
    if code_grader is not None:
        eval_graph.add_node("code_grader", _create_code_grader_node(code_grader))
    else:
        eval_graph.add_node(
            "code_grader", _create_passthrough_node("code_grader", "code_grader_result", 1)
        )

    # L2 LLM Grader 노드
    if llm_grader is not None:
        eval_graph.add_node("llm_grader", _create_llm_grader_node(llm_grader))
    else:
        eval_graph.add_node(
            "llm_grader", _create_passthrough_node("llm_grader", "llm_grader_result", 2)
        )

    # L3 Calibration Check 노드
    if calibration_monitor is not None:
        eval_graph.add_node("calibration_check", _create_calibration_node(calibration_monitor))
    else:
        eval_graph.add_node(
            "calibration_check",
            _create_passthrough_node("calibration_check", "calibration_result", 3),
        )

    # Aggregator + Decision 노드
    if score_aggregator is not None:
        eval_graph.add_node(
            "eval_aggregator", _create_eval_aggregator_node(score_aggregator, eval_config)
        )
    else:
        eval_graph.add_node("eval_aggregator", _create_passthrough_aggregator())

    eval_graph.add_node("eval_decision", _create_eval_decision_node(eval_config))

    # Entry → Parallel fan-out via Send API
    eval_graph.set_entry_point("eval_entry")
    eval_graph.add_conditional_edges(
        "eval_entry",
        route_to_graders,  # Returns list[Send]
    )

    # Fan-in to aggregator
    eval_graph.add_edge("code_grader", "eval_aggregator")
    eval_graph.add_edge("llm_grader", "eval_aggregator")
    eval_graph.add_edge("calibration_check", "eval_aggregator")

    # Aggregator → Decision → END
    eval_graph.add_edge("eval_aggregator", "eval_decision")
    eval_graph.add_edge("eval_decision", END)

    logger.info(
        "Eval subgraph created",
        extra={
            "eval_mode": eval_config.eval_mode,
            "llm_grader_enabled": eval_config.eval_llm_grader_enabled,
            "regeneration_enabled": eval_config.eval_regeneration_enabled,
            "has_code_grader": code_grader is not None,
            "has_llm_grader": llm_grader is not None,
            "has_calibration": calibration_monitor is not None,
            "has_aggregator": score_aggregator is not None,
        },
    )

    return eval_graph.compile()


# ============================================================
# Passthrough Nodes (서비스 미주입 시 fallback)
# ============================================================


def _create_passthrough_node(name: str, result_key: str, priority: int):
    """서비스 미주입 시 기본값 반환 passthrough 노드."""

    async def passthrough(state: dict[str, Any]) -> dict[str, Any]:
        logger.debug("%s: passthrough (service not injected)", name)
        return {
            result_key: {
                "success": True,
                "_priority": priority,
                "_sequence": 0,
            },
        }

    return passthrough


def _create_passthrough_aggregator():
    """ScoreAggregator 미주입 시 기본 B등급 반환."""

    async def passthrough_aggregator(state: dict[str, Any]) -> dict[str, Any]:
        if state.get("_entry_failed"):
            return {
                "eval_result": state.get("eval_result", {"degraded": True}),
                "eval_grade": state.get("eval_grade", "B"),
                "eval_continuous_score": state.get("eval_continuous_score", 0.0),
                "eval_needs_regeneration": False,
                "eval_improvement_hints": [],
            }
        return {
            "eval_result": {"passthrough": True},
            "eval_grade": "B",
            "eval_continuous_score": 65.0,
            "eval_needs_regeneration": False,
            "eval_improvement_hints": [],
        }

    return passthrough_aggregator


__all__ = [
    "EvalState",
    "MINIMUM_IMPROVEMENT_THRESHOLD",
    "create_eval_subgraph",
    "create_route_after_eval",
    "route_to_graders",
]
