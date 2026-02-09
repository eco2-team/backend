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
from chat_worker.application.dto.eval_result import EvalResult

logger = logging.getLogger(__name__)


def _should_calibrate(state: dict[str, Any], eval_config: EvalConfig) -> bool:
    """Calibration 실행 여부 판단 (fallback).

    eval_counter가 주입되지 않았을 때의 stopgap fallback.
    eval_retry_count 기반 단순 판단.

    Args:
        state: 현재 상태
        eval_config: Eval 설정

    Returns:
        Calibration 실행 여부
    """
    interval = eval_config.eval_cusum_check_interval
    if interval <= 0:
        return False
    # stopgap: retry_count 기반 주기 판단 (eval_counter 미주입 시 fallback)
    retry_count = state.get("eval_retry_count", 0)
    return retry_count > 0 and (retry_count % interval) == 0


def _make_failed_eval_result(reason: str) -> dict[str, Any]:
    """FAIL_OPEN 기본값 생성.

    EvalResult.failed()를 사용하여 B등급 기본값을 생성합니다.
    Grade C (< 55) triggers regeneration, but eval failure must NOT
    trigger regeneration — only genuinely low-quality answers should.

    See: docs/plans/chat-eval-pipeline-plan.md A.12

    Args:
        reason: 실패 사유

    Returns:
        실패 상태의 eval 결과 dict (ChatState 호환)
    """
    failed = EvalResult.failed(reason)
    return {
        "eval_result": failed.to_dict(),
        "eval_grade": failed.grade,
        "eval_continuous_score": failed.continuous_score,
        "eval_needs_regeneration": False,
        "eval_improvement_hints": [],
        "eval_retry_count": 0,
        "_prev_eval_score": None,
    }


def create_eval_entry_node(eval_config: EvalConfig, eval_counter=None):
    """Eval entry 노드 팩토리.

    서브그래프 entry point. 부모 ChatState에서 EvalState로 필드 매핑.
    LangGraph는 서브그래프 호출 시 부모 state를 그대로 전달하므로,
    entry 노드에서 필드 매핑이 자연스럽게 수행됨.

    에러 처리: try/except로 감싸고, 실패 시 _entry_failed=True 플래그를
    설정하여 route_to_graders에서 short-circuit.

    See: docs/plans/chat-eval-pipeline-plan.md B.3

    Args:
        eval_config: Eval Pipeline 설정
        eval_counter: RedisEvalCounter (None이면 stopgap fallback)

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
            # Calibration 실행 여부: eval_counter 우선, 없으면 stopgap
            if eval_counter is not None:
                try:
                    _count, should_calibrate = await eval_counter.increment_and_check()
                except Exception as e:
                    logger.warning("eval_counter failed, falling back to stopgap: %s", e)
                    should_calibrate = _should_calibrate(state, eval_config)
            else:
                should_calibrate = _should_calibrate(state, eval_config)

            retry_count = state.get("eval_retry_count", 0)

            logger.info(
                "eval_entry: state mapped",
                extra={
                    "intent": state.get("intent"),
                    "answer_len": len(state.get("answer", "")),
                    "should_calibrate": should_calibrate,
                    "eval_retry_count": retry_count,
                    "has_counter": eval_counter is not None,
                },
            )

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
                "should_run_calibration": should_calibrate,
                "eval_retry_count": retry_count,
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
