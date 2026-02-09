"""Eval Subgraph ↔ ChatState 키 정합성 검증 테스트.

EvalState의 Aggregated Output 키가 ChatState에 모두 존재하는지 검증합니다.
서브그래프 결과가 부모 그래프로 전파될 때 누락이 없어야 합니다.

See: docs/plans/chat-eval-pipeline-plan.md §2.3, §2.6
"""

from __future__ import annotations

import pytest

from chat_worker.infrastructure.orchestration.langgraph.eval_graph_factory import (
    EvalState,
)
from chat_worker.infrastructure.orchestration.langgraph.state import ChatState


# ChatState Layer 8 eval 키 (설계안 §2.6에서 정의)
_EXPECTED_CHAT_STATE_EVAL_KEYS: frozenset[str] = frozenset(
    {
        "eval_result",
        "eval_grade",
        "eval_continuous_score",
        "eval_needs_regeneration",
        "eval_retry_count",
        "eval_improvement_hints",
        "_prev_eval_score",
    }
)

# EvalState에서 ChatState로 전파되어야 하는 키
_EVAL_OUTPUT_KEYS: frozenset[str] = frozenset(
    {
        "eval_result",
        "eval_grade",
        "eval_continuous_score",
        "eval_needs_regeneration",
        "eval_improvement_hints",
        "_prev_eval_score",
    }
)


@pytest.mark.eval_unit
class TestEvalSubgraphKeyAlignment:
    """EvalState ↔ ChatState 키 정합성 테스트."""

    def test_chat_state_has_all_expected_eval_keys(self) -> None:
        """ChatState에 Layer 8 eval 키가 모두 존재한다."""
        chat_state_keys = set(ChatState.__annotations__.keys())

        missing = _EXPECTED_CHAT_STATE_EVAL_KEYS - chat_state_keys
        assert not missing, f"ChatState에 누락된 eval 키: {missing}"

    def test_eval_state_has_all_output_keys(self) -> None:
        """EvalState에 Aggregated Output 키가 모두 존재한다."""
        eval_state_keys = set(EvalState.__annotations__.keys())

        missing = _EVAL_OUTPUT_KEYS - eval_state_keys
        assert not missing, f"EvalState에 누락된 output 키: {missing}"

    def test_output_keys_subset_of_chat_state(self) -> None:
        """EvalState output 키가 ChatState의 부분집합이다."""
        chat_state_keys = set(ChatState.__annotations__.keys())

        # EvalState의 Aggregated Output + Internal 키 중 ChatState에도 있어야 하는 것
        not_in_chat = _EVAL_OUTPUT_KEYS - chat_state_keys
        assert not not_in_chat, f"EvalState output 키가 ChatState에 없음: {not_in_chat}"

    def test_eval_state_has_grader_channels(self) -> None:
        """EvalState에 3개 Grader 결과 채널이 존재한다."""
        eval_keys = set(EvalState.__annotations__.keys())
        grader_keys = {"code_grader_result", "llm_grader_result", "calibration_result"}

        missing = grader_keys - eval_keys
        assert not missing, f"EvalState에 누락된 grader 채널: {missing}"

    def test_eval_state_input_keys(self) -> None:
        """EvalState에 Input 키가 존재한다."""
        eval_keys = set(EvalState.__annotations__.keys())
        input_keys = {"query", "intent", "answer", "rag_context", "conversation_history"}

        missing = input_keys - eval_keys
        assert not missing, f"EvalState에 누락된 input 키: {missing}"
