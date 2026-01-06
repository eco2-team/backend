"""VisionStep Unit Tests."""

from __future__ import annotations

from typing import Any

import pytest

from scan_worker.application.classify.dto.classify_context import ClassifyContext
from scan_worker.application.classify.ports.prompt_repository import (
    PromptRepositoryPort,
)
from scan_worker.application.classify.ports.vision_model import VisionModelPort

# ============================================================
# Mock Implementations
# ============================================================


class MockVisionModel(VisionModelPort):
    """Mock Vision Model for testing."""

    def __init__(self, return_value: dict[str, Any] | None = None):
        self._return_value = return_value or {
            "classification": {
                "major_category": "재활용폐기물",
                "middle_category": "플라스틱류",
                "minor_category": "페트병",
            },
            "situation_tags": ["깨끗한 상태", "라벨 부착"],
            "meta": {"user_input": "테스트"},
        }
        self.last_user_input = None  # 호출 확인용

    def analyze_image(
        self,
        prompt: str,
        image_url: str,
        user_input: str | None = None,
    ) -> dict[str, Any]:
        self.last_user_input = user_input
        return self._return_value


class MockPromptRepository(PromptRepositoryPort):
    """Mock Prompt Repository for testing."""

    def get_prompt(self, name: str) -> str:
        return "Test prompt template with {{ITEM_CLASS_YAML}} and {{SITUATION_TAG_YAML}}"

    def get_classification_schema(self) -> dict[str, Any]:
        return {"대분류": {"재활용폐기물": {"중분류": ["플라스틱류"]}}}

    def get_situation_tags(self) -> dict[str, Any]:
        return {"상태": ["깨끗한 상태", "오염된 상태"]}


# ============================================================
# Tests
# ============================================================


class TestVisionStep:
    """VisionStep 단위 테스트."""

    def test_run_success(self):
        """정상 실행 테스트."""
        # Delayed import to avoid Celery dependency
        from scan_worker.application.classify.steps.vision_step import VisionStep

        # Given
        vision_model = MockVisionModel()
        prompt_repo = MockPromptRepository()
        step = VisionStep(vision_model, prompt_repo)

        ctx = ClassifyContext(
            task_id="test-task-001",
            user_id="user-001",
            image_url="https://example.com/image.jpg",
            user_input="이 폐기물은 무엇인가요?",
        )

        # When
        result = step.run(ctx)

        # Then
        assert result.classification is not None
        assert result.classification["classification"]["major_category"] == "재활용폐기물"
        assert result.progress == 25
        assert "duration_vision_ms" in result.latencies

    def test_run_with_situation_tags(self):
        """상황 태그 포함 테스트."""
        from scan_worker.application.classify.steps.vision_step import VisionStep

        # Given
        vision_model = MockVisionModel()
        prompt_repo = MockPromptRepository()
        step = VisionStep(vision_model, prompt_repo)

        ctx = ClassifyContext(
            task_id="test-task-002",
            user_id="user-002",
            image_url="https://example.com/image.jpg",
        )

        # When
        result = step.run(ctx)

        # Then
        assert result.classification is not None
        assert "situation_tags" in result.classification
        assert len(result.classification["situation_tags"]) > 0

    def test_prompt_rendering(self):
        """프롬프트 렌더링 테스트."""
        from scan_worker.application.classify.steps.vision_step import VisionStep

        # Given
        vision_model = MockVisionModel()
        prompt_repo = MockPromptRepository()
        step = VisionStep(vision_model, prompt_repo)

        template = "분류: {{ITEM_CLASS_YAML}}\n태그: {{SITUATION_TAG_YAML}}"
        schema = {"분류체계": "테스트"}
        tags = {"태그": "테스트"}

        # When
        rendered = step._render_prompt(template, schema, tags, None)

        # Then
        assert "{{ITEM_CLASS_YAML}}" not in rendered
        assert "{{SITUATION_TAG_YAML}}" not in rendered
        assert "분류체계" in rendered

    def test_user_input_passed_to_vision_model(self):
        """user_input이 VisionModel에 전달되는지 테스트."""
        from scan_worker.application.classify.steps.vision_step import VisionStep

        # Given
        vision_model = MockVisionModel()
        prompt_repo = MockPromptRepository()
        step = VisionStep(vision_model, prompt_repo)

        ctx = ClassifyContext(
            task_id="test-task-003",
            user_id="user-003",
            image_url="https://example.com/image.jpg",
            user_input="이 폐기물을 어떻게 버려야 하나요?",
        )

        # When
        step.run(ctx)

        # Then
        assert vision_model.last_user_input == "이 폐기물을 어떻게 버려야 하나요?"

    def test_user_input_none_passed(self):
        """user_input이 None일 때 None이 전달되는지 테스트."""
        from scan_worker.application.classify.steps.vision_step import VisionStep

        # Given
        vision_model = MockVisionModel()
        prompt_repo = MockPromptRepository()
        step = VisionStep(vision_model, prompt_repo)

        ctx = ClassifyContext(
            task_id="test-task-004",
            user_id="user-004",
            image_url="https://example.com/image.jpg",
            user_input=None,  # 명시적 None
        )

        # When
        step.run(ctx)

        # Then
        assert vision_model.last_user_input is None


class TestClassifyContext:
    """ClassifyContext 테스트."""

    def test_to_dict_and_from_dict(self):
        """직렬화/역직렬화 테스트."""
        # Given
        ctx = ClassifyContext(
            task_id="test-task",
            user_id="user-001",
            image_url="https://example.com/image.jpg",
            user_input="테스트 입력",
            llm_provider="openai",
            llm_model="gpt-5.1",
            classification={"classification": {"major_category": "테스트"}},
            progress=50,
        )

        # When
        serialized = ctx.to_dict()
        restored = ClassifyContext.from_dict(serialized)

        # Then
        assert restored.task_id == ctx.task_id
        assert restored.user_id == ctx.user_id
        assert restored.image_url == ctx.image_url
        assert restored.llm_provider == ctx.llm_provider
        assert restored.llm_model == ctx.llm_model
        assert restored.progress == ctx.progress


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
