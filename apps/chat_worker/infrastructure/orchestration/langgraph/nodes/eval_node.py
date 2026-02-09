"""Eval Node - LangGraph 어댑터.

얇은 어댑터: ChatState → EvalState 필드 매핑 + error fallback.
Eval Pipeline 서브그래프의 진입점.

Clean Architecture:
- Node(Adapter): 이 파일 - LangGraph glue code (state 변환만 담당)
- Subgraph: eval_graph_factory.py - 내부 eval 파이프라인

See: docs/plans/chat-eval-pipeline-plan.md B.3
"""

from __future__ import annotations

import logging
from typing import Any

from chat_worker.application.dto.eval_config import EvalConfig

logger = logging.getLogger(__name__)


def _should_calibrate(state: dict[str, Any], eval_config: EvalConfig) -> bool:
    """Calibration 실행 여부 판단.

    eval_cusum_check_interval 주기마다 Calibration Check를 실행합니다.
    현재는 eval_retry_count 기반 단순 판단 (향후 global request counter로 전환).

    TODO(#calibration-trigger): global request counter 기반으로 전환 예정.
    현재 stopgap: eval_retry_count를 interval로 나눠 주기 판단.
    실제 request counter는 Redis INCR 등으로 구현 필요.

    Args:
        state: 현재 상태
        eval_config: Eval 설정

    Returns:
        Calibration 실행 여부
    """
    interval = eval_config.eval_cusum_check_interval
    if interval <= 0:
        return False
    # stopgap: retry_count 기반 주기 판단 (global counter 미구현 시 fallback)
    retry_count = state.get("eval_retry_count", 0)
    return retry_count > 0 and (retry_count % interval) == 0


def _make_failed_eval_result(reason: str) -> dict[str, Any]:
    """EvalResult.failed() 대응 기본값 생성.

    EvalResult DTO가 아직 구현되지 않은 상태에서 사용하는
    인라인 fallback 생성기. DTO 구현 후 EvalResult.failed()로 대체.

    See: docs/plans/chat-eval-pipeline-plan.md A.12

    Args:
        reason: 실패 사유

    Returns:
        실패 상태의 eval 결과 dict
    """
    # Fallback grade = "B" (not "C"): FAIL_OPEN policy.
    # Grade C (< 55) triggers regeneration, but eval failure must NOT
    # trigger regeneration — only genuinely low-quality answers should.
    # See plan A.12 + NodePolicy eval.fail_mode=FAIL_OPEN.
    return {
        "eval_result": {"error": reason, "degraded": True},
        "eval_grade": "B",
        "eval_continuous_score": 65.0,
        "eval_needs_regeneration": False,
        "eval_improvement_hints": [],
        "eval_retry_count": 0,
        "_prev_eval_score": None,
    }


def create_eval_entry_node(eval_config: EvalConfig):
    """Eval entry 노드 팩토리.

    서브그래프 entry point. 부모 ChatState에서 EvalState로 필드 매핑.
    LangGraph는 서브그래프 호출 시 부모 state를 그대로 전달하므로,
    entry 노드에서 필드 매핑이 자연스럽게 수행됨.

    에러 처리: try/except로 감싸고, 실패 시 _entry_failed=True 플래그를
    설정하여 route_to_graders에서 short-circuit.

    See: docs/plans/chat-eval-pipeline-plan.md B.3

    Args:
        eval_config: Eval Pipeline 설정

    Returns:
        eval_entry 노드 함수
    """

    async def eval_entry(state: dict[str, Any]) -> dict[str, Any]:
        """서브그래프 entry 노드. ChatState → EvalState 필드 매핑.

        Args:
            state: 부모 ChatState (LangGraph가 자동 전달)

        Returns:
            EvalState 필드가 매핑된 dict
        """
        try:
            return {
                # ChatState → EvalState 필드 매핑
                "query": state.get("message", ""),
                "intent": state.get("intent", ""),
                "answer": state.get("answer", ""),
                "rag_context": state.get("disposal_rules"),
                "conversation_history": state.get("conversation_history", []),
                "feedback_result": state.get("rag_feedback"),
                # Config injection
                "llm_grader_enabled": eval_config.eval_llm_grader_enabled,
                "should_run_calibration": _should_calibrate(state, eval_config),
                "eval_retry_count": state.get("eval_retry_count", 0),
                "_prev_eval_score": state.get("eval_continuous_score"),
            }

        except Exception as e:
            logger.warning(
                "eval_entry failed, using degraded fallback",
                extra={"error": str(e)},
            )
            failed = _make_failed_eval_result(f"eval_entry: {e}")
            failed["_entry_failed"] = True  # short-circuit 시그널
            return failed

    return eval_entry


__all__ = [
    "create_eval_entry_node",
]
