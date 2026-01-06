"""ClassifyPipeline Integration Tests."""

from __future__ import annotations

from typing import Any

import pytest

from scan_worker.application.classify.dto.classify_context import ClassifyContext
from scan_worker.application.classify.ports.event_publisher import (
    EventPublisherPort,
)
from scan_worker.application.classify.ports.llm_model import LLMPort
from scan_worker.application.classify.ports.prompt_repository import (
    PromptRepositoryPort,
)
from scan_worker.application.classify.ports.retriever import RetrieverPort
from scan_worker.application.classify.ports.vision_model import VisionModelPort

# ============================================================
# Mock Implementations
# ============================================================


class MockVisionModel(VisionModelPort):
    """Mock Vision Model."""

    def analyze_image(self, prompt: str, image_url: str) -> dict[str, Any]:
        return {
            "classification": {
                "major_category": "재활용폐기물",
                "middle_category": "플라스틱류",
                "minor_category": "페트병",
            },
            "situation_tags": ["깨끗한 상태"],
            "meta": {"user_input": ""},
        }


class MockRetriever(RetrieverPort):
    """Mock Retriever."""

    def get_disposal_rules(self, classification: dict[str, Any]) -> dict[str, Any] | None:
        return {
            "규정명": "플라스틱류 배출 규정",
            "배출방법": "내용물 비우고 물로 헹궈서 배출",
        }


class MockLLM(LLMPort):
    """Mock LLM."""

    def generate_answer(
        self,
        classification: dict[str, Any],
        disposal_rules: dict[str, Any],
        user_input: str,
        system_prompt: str | None = None,
    ) -> dict[str, Any]:
        return {
            "disposal_steps": {"단계1": "내용물을 비웁니다."},
            "insufficiencies": [],
            "user_answer": "페트병은 내용물을 비우고 배출하세요.",
        }


class MockPromptRepository(PromptRepositoryPort):
    """Mock Prompt Repository."""

    def get_prompt(self, name: str) -> str:
        return "Test prompt {{ITEM_CLASS_YAML}} {{SITUATION_TAG_YAML}}"

    def get_classification_schema(self) -> dict[str, Any]:
        return {"분류": "테스트"}

    def get_situation_tags(self) -> dict[str, Any]:
        return {"태그": "테스트"}


class MockEventPublisher(EventPublisherPort):
    """Mock Event Publisher."""

    def __init__(self):
        self.events: list[dict] = []

    def publish_stage_event(
        self,
        task_id: str,
        stage: str,
        status: str,
        progress: int | None = None,
        result: dict[str, Any] | None = None,
    ) -> str:
        self.events.append(
            {
                "task_id": task_id,
                "stage": stage,
                "status": status,
                "progress": progress,
                "result": result,
            }
        )
        return f"mock-msg-{len(self.events)}"


# ============================================================
# Tests
# ============================================================


class TestClassifyPipeline:
    """ClassifyPipeline 통합 테스트."""

    def _create_pipeline_with_mocks(self):
        """Mock을 사용한 파이프라인 생성."""
        # Delayed imports to avoid Celery dependency
        from scan_worker.application.classify.commands.execute_pipeline import (
            ClassifyPipeline,
        )
        from scan_worker.application.classify.steps.answer_step import AnswerStep
        from scan_worker.application.classify.steps.rule_step import RuleStep
        from scan_worker.application.classify.steps.vision_step import VisionStep

        vision_model = MockVisionModel()
        retriever = MockRetriever()
        llm = MockLLM()
        prompt_repo = MockPromptRepository()
        event_publisher = MockEventPublisher()

        steps = [
            ("vision", VisionStep(vision_model, prompt_repo)),
            ("rule", RuleStep(retriever)),
            ("answer", AnswerStep(llm, prompt_repo)),
        ]

        pipeline = ClassifyPipeline(
            steps=steps,
            event_publisher=event_publisher,
        )

        return pipeline, event_publisher

    def test_full_pipeline_success(self):
        """전체 파이프라인 성공 테스트."""
        # Given
        pipeline, events = self._create_pipeline_with_mocks()

        ctx = ClassifyContext(
            task_id="test-task-001",
            user_id="user-001",
            image_url="https://example.com/image.jpg",
        )

        # When
        result = pipeline.execute(ctx)

        # Then
        assert result.classification is not None
        assert result.disposal_rules is not None
        assert result.final_answer is not None
        assert result.progress == 75  # answer 완료 후
        assert result.error is None

        # 이벤트 발행 확인
        assert len(events.events) == 6  # started + completed for 3 steps

    def test_pipeline_publishes_events(self):
        """파이프라인 이벤트 발행 테스트."""
        # Given
        pipeline, events = self._create_pipeline_with_mocks()

        ctx = ClassifyContext(
            task_id="test-task-002",
            user_id="user-002",
            image_url="https://example.com/image.jpg",
        )

        # When
        pipeline.execute(ctx)

        # Then
        stages_started = [e["stage"] for e in events.events if e["status"] == "started"]
        stages_completed = [e["stage"] for e in events.events if e["status"] == "completed"]

        assert stages_started == ["vision", "rule", "answer"]
        assert stages_completed == ["vision", "rule", "answer"]

    def test_pipeline_error_handling(self):
        """파이프라인 에러 처리 테스트."""
        from scan_worker.application.classify.commands.execute_pipeline import (
            ClassifyPipeline,
        )
        from scan_worker.application.classify.steps.vision_step import VisionStep

        # Given
        event_publisher = MockEventPublisher()

        class FailingVisionModel(VisionModelPort):
            def analyze_image(self, prompt: str, image_url: str) -> dict[str, Any]:
                raise RuntimeError("Vision API error")

        prompt_repo = MockPromptRepository()
        steps = [
            ("vision", VisionStep(FailingVisionModel(), prompt_repo)),
        ]

        pipeline = ClassifyPipeline(
            steps=steps,
            event_publisher=event_publisher,
        )

        ctx = ClassifyContext(
            task_id="test-task-003",
            user_id="user-003",
            image_url="https://example.com/image.jpg",
        )

        # When
        result = pipeline.execute(ctx)

        # Then
        assert result.error is not None
        assert "Vision API error" in result.error

        # 실패 이벤트 확인
        failed_events = [e for e in event_publisher.events if e["status"] == "failed"]
        assert len(failed_events) == 1
        assert failed_events[0]["stage"] == "vision"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
