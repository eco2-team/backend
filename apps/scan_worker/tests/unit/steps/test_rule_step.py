"""RuleStep Unit Tests."""

from __future__ import annotations

from typing import Any

import pytest

from scan_worker.application.classify.dto.classify_context import ClassifyContext
from scan_worker.application.classify.ports.retriever import RetrieverPort

# ============================================================
# Mock Implementations
# ============================================================


class MockRetriever(RetrieverPort):
    """Mock Retriever for testing."""

    def __init__(self, return_value: dict[str, Any] | None = None):
        self._return_value = return_value

    def get_disposal_rules(self, classification: dict[str, Any]) -> dict[str, Any] | None:
        if self._return_value is not None:
            return self._return_value

        # 기본 매칭 로직
        cls = classification.get("classification", {})
        major = cls.get("major_category", "")
        if major == "재활용폐기물":
            return {
                "규정명": "플라스틱류 배출 규정",
                "배출방법": "내용물 비우고 물로 헹궈서 배출",
            }
        return None


class MockRetrieverNoMatch(RetrieverPort):
    """항상 None을 반환하는 Mock Retriever."""

    def get_disposal_rules(self, classification: dict[str, Any]) -> dict[str, Any] | None:
        return None


# ============================================================
# Tests
# ============================================================


class TestRuleStep:
    """RuleStep 단위 테스트."""

    def test_run_with_matching_rules(self):
        """규정 매칭 성공 테스트."""
        # Delayed import to avoid Celery dependency
        from scan_worker.application.classify.steps.rule_step import RuleStep

        # Given
        retriever = MockRetriever()
        step = RuleStep(retriever)

        ctx = ClassifyContext(
            task_id="test-task-001",
            user_id="user-001",
            image_url="https://example.com/image.jpg",
            classification={
                "classification": {
                    "major_category": "재활용폐기물",
                    "middle_category": "플라스틱류",
                }
            },
            progress=25,
        )

        # When
        result = step.run(ctx)

        # Then
        assert result.disposal_rules is not None
        assert "규정명" in result.disposal_rules
        assert result.progress == 50
        assert "duration_rule_ms" in result.latencies

    def test_run_without_classification(self):
        """분류 결과 없을 때 스킵 테스트."""
        from scan_worker.application.classify.steps.rule_step import RuleStep

        # Given
        retriever = MockRetriever()
        step = RuleStep(retriever)

        ctx = ClassifyContext(
            task_id="test-task-002",
            user_id="user-002",
            image_url="https://example.com/image.jpg",
            classification=None,  # 분류 결과 없음
            progress=25,
        )

        # When
        result = step.run(ctx)

        # Then
        assert result.disposal_rules is None
        assert result.progress == 50  # progress는 업데이트됨

    def test_run_without_matching_rules(self):
        """규정 매칭 실패 테스트."""
        from scan_worker.application.classify.steps.rule_step import RuleStep

        # Given
        retriever = MockRetrieverNoMatch()
        step = RuleStep(retriever)

        ctx = ClassifyContext(
            task_id="test-task-003",
            user_id="user-003",
            image_url="https://example.com/image.jpg",
            classification={
                "classification": {
                    "major_category": "알수없음",
                    "middle_category": "기타",
                }
            },
            progress=25,
        )

        # When
        result = step.run(ctx)

        # Then
        assert result.disposal_rules is None
        assert result.progress == 50


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
