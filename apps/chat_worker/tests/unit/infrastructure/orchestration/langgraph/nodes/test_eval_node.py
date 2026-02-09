"""Eval Node Unit Tests."""

from __future__ import annotations

import pytest

from chat_worker.application.dto.eval_config import EvalConfig
from chat_worker.infrastructure.orchestration.langgraph.nodes.eval_node import (
    _make_failed_eval_result,
    create_eval_entry_node,
)


@pytest.mark.eval_unit
class TestEvalEntryNode:
    """eval_entry 노드 테스트."""

    async def test_eval_entry_maps_fields_correctly(self) -> None:
        """ChatState → EvalState 필드 매핑 검증."""
        node = create_eval_entry_node(EvalConfig())
        state = {
            "message": "플라스틱 분리배출 방법",
            "intent": "waste",
            "answer": "페트병은 라벨을 제거하고 분리배출합니다.",
            "disposal_rules": ["규칙1", "규칙2"],
            "conversation_history": [{"role": "user", "content": "안녕"}],
            "rag_feedback": {"score": 0.8},
            "eval_retry_count": 1,
            "eval_continuous_score": 75.0,
        }

        result = await node(state)

        assert result["query"] == "플라스틱 분리배출 방법"
        assert result["intent"] == "waste"
        assert result["answer"] == "페트병은 라벨을 제거하고 분리배출합니다."
        assert result["rag_context"] == ["규칙1", "규칙2"]
        assert result["conversation_history"] == [{"role": "user", "content": "안녕"}]
        assert result["feedback_result"] == {"score": 0.8}
        assert result["eval_retry_count"] == 1
        assert result["_prev_eval_score"] == 75.0

    async def test_eval_entry_defaults_for_missing_fields(self) -> None:
        """누락 필드에 기본값 적용."""
        node = create_eval_entry_node(EvalConfig())
        state: dict = {}

        result = await node(state)

        assert result["query"] == ""
        assert result["intent"] == ""
        assert result["answer"] == ""
        assert result["rag_context"] is None
        assert result["conversation_history"] == []
        assert result["feedback_result"] is None
        assert result["eval_retry_count"] == 0
        assert result["_prev_eval_score"] is None

    async def test_eval_entry_failure_sets_entry_failed_flag(self) -> None:
        """eval_entry 실패 시 _entry_failed=True 설정."""
        config = EvalConfig()
        node = create_eval_entry_node(config)

        # state.get()이 예외를 발생시키도록 비정상 객체 전달
        class BrokenState:
            def get(self, key, default=None):
                raise RuntimeError("state broken")

        result = await node(BrokenState())  # type: ignore

        assert result["_entry_failed"] is True

    async def test_eval_entry_failure_grade_is_b(self) -> None:
        """eval_entry 실패 시 등급은 B (C가 아님)."""
        config = EvalConfig()
        node = create_eval_entry_node(config)

        class BrokenState:
            def get(self, key, default=None):
                raise RuntimeError("state broken")

        result = await node(BrokenState())  # type: ignore

        assert result["eval_grade"] == "B"
        assert result["eval_needs_regeneration"] is False


@pytest.mark.eval_unit
class TestMakeFailedEvalResult:
    """_make_failed_eval_result 헬퍼 테스트."""

    def test_make_failed_eval_result_structure(self) -> None:
        """실패 결과 딕셔너리 구조 검증."""
        result = _make_failed_eval_result("테스트 실패 사유")

        assert result["eval_result"]["error"] == "테스트 실패 사유"
        assert result["eval_result"]["degraded"] is True
        assert result["eval_grade"] == "B"
        assert result["eval_continuous_score"] == 65.0
        assert result["eval_needs_regeneration"] is False
        assert result["eval_improvement_hints"] == []
        assert result["eval_retry_count"] == 0
        assert result["_prev_eval_score"] is None
