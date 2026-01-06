"""AnswerStep Unit Tests."""

from __future__ import annotations

from typing import Any

import pytest

from scan_worker.application.classify.dto.classify_context import ClassifyContext
from scan_worker.application.classify.ports.llm_model import LLMPort
from scan_worker.application.classify.ports.prompt_repository import (
    PromptRepositoryPort,
)

# ============================================================
# Mock Implementations
# ============================================================


class MockLLM(LLMPort):
    """Mock LLM for testing."""

    def __init__(self, return_value: dict[str, Any] | None = None):
        self._return_value = return_value or {
            "disposal_steps": {
                "단계1": "내용물을 비웁니다.",
                "단계2": "물로 깨끗이 헹굽니다.",
                "단계3": "라벨을 제거합니다.",
                "단계4": "분리수거함에 배출합니다.",
            },
            "insufficiencies": [],
            "user_answer": "페트병은 내용물을 비우고 물로 헹군 후 라벨을 제거하여 분리수거함에 배출하세요.",
        }

    def generate_answer(
        self,
        classification: dict[str, Any],
        disposal_rules: dict[str, Any],
        user_input: str,
        system_prompt: str | None = None,
    ) -> dict[str, Any]:
        return self._return_value


class MockPromptRepository(PromptRepositoryPort):
    """Mock Prompt Repository for testing."""

    def get_prompt(self, name: str) -> str:
        if name == "answer_generation_prompt":
            return "당신은 폐기물 분리배출 전문가입니다."
        raise FileNotFoundError(f"Prompt not found: {name}")

    def get_classification_schema(self) -> dict[str, Any]:
        return {}

    def get_situation_tags(self) -> dict[str, Any]:
        return {}


# ============================================================
# Tests
# ============================================================


class TestAnswerStep:
    """AnswerStep 단위 테스트."""

    def test_run_with_disposal_rules(self):
        """배출 규정 있을 때 답변 생성 테스트."""
        # Delayed import to avoid Celery dependency
        from scan_worker.application.classify.steps.answer_step import AnswerStep

        # Given
        llm = MockLLM()
        prompt_repo = MockPromptRepository()
        step = AnswerStep(llm, prompt_repo)

        ctx = ClassifyContext(
            task_id="test-task-001",
            user_id="user-001",
            image_url="https://example.com/image.jpg",
            classification={"classification": {"major_category": "재활용폐기물"}},
            disposal_rules={
                "규정명": "플라스틱류 배출 규정",
                "배출방법": "내용물 비우고 물로 헹궈서 배출",
            },
            progress=50,
        )

        # When
        result = step.run(ctx)

        # Then
        assert result.final_answer is not None
        assert "disposal_steps" in result.final_answer
        assert "user_answer" in result.final_answer
        assert result.progress == 75
        assert "duration_answer_ms" in result.latencies

    def test_run_without_disposal_rules(self):
        """배출 규정 없을 때 fallback 답변 테스트."""
        from scan_worker.application.classify.steps.answer_step import AnswerStep

        # Given
        llm = MockLLM()
        prompt_repo = MockPromptRepository()
        step = AnswerStep(llm, prompt_repo)

        ctx = ClassifyContext(
            task_id="test-task-002",
            user_id="user-002",
            image_url="https://example.com/image.jpg",
            classification={"classification": {"major_category": "알수없음"}},
            disposal_rules=None,  # 규정 없음
            progress=50,
        )

        # When
        result = step.run(ctx)

        # Then
        assert result.final_answer is not None
        assert "배출 규정 매칭 실패" in result.final_answer.get("insufficiencies", [])
        assert result.progress == 75

    def test_run_calculates_total_duration(self):
        """총 소요시간 계산 테스트."""
        from scan_worker.application.classify.steps.answer_step import AnswerStep

        # Given
        llm = MockLLM()
        prompt_repo = MockPromptRepository()
        step = AnswerStep(llm, prompt_repo)

        ctx = ClassifyContext(
            task_id="test-task-003",
            user_id="user-003",
            image_url="https://example.com/image.jpg",
            classification={"classification": {"major_category": "재활용폐기물"}},
            disposal_rules={"규정": "테스트"},
            latencies={
                "duration_vision_ms": 1000.0,
                "duration_rule_ms": 100.0,
            },
            progress=50,
        )

        # When
        result = step.run(ctx)

        # Then
        assert "duration_total_ms" in result.latencies
        total = result.latencies["duration_total_ms"]
        assert total > 1100  # vision + rule + answer


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
