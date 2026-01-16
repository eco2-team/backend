"""Vision Flow Integration Tests.

이미지 분류 → RAG → 답변 흐름 통합 테스트.
"""

from __future__ import annotations

from typing import Any

import pytest

from chat_worker.infrastructure.orchestration.langgraph.nodes.vision_node import (
    create_vision_node,
)
from chat_worker.infrastructure.orchestration.langgraph.nodes.rag_node import (
    create_rag_node,
)


class MockVisionModel:
    """Mock Vision Model."""

    def __init__(self, return_value: dict | None = None):
        self._return_value = return_value or {
            "classification": {
                "major_category": "재활용폐기물",
                "middle_category": "플라스틱류",
                "minor_category": "페트병",
            },
            "situation_tags": ["세척필요", "라벨제거"],
            "confidence": 0.92,
        }

    async def analyze_image(self, image_url: str, user_input: str | None = None) -> dict[str, Any]:
        return self._return_value


class MockRetriever:
    """Mock Retriever."""

    def __init__(self):
        self.search_called = False
        self.search_args = None

    def search(self, category: str, subcategory: str) -> dict | None:
        self.search_called = True
        self.search_args = (category, subcategory)
        return {
            "category": category,
            "subcategory": subcategory,
            "disposal_method": "깨끗이 씻어서 라벨을 제거한 후 분리수거함에 배출",
            "tips": ["뚜껑은 따로 분리", "내용물 비우기"],
        }

    def search_by_keyword(self, keyword: str, limit: int = 5) -> list:
        return []


class MockProgressNotifier:
    """Mock Progress Notifier."""

    def __init__(self):
        self.events: list[dict] = []

    async def notify_stage(self, **kwargs):
        self.events.append(kwargs)

    async def notify_token(self, **kwargs):
        self.events.append({"type": "token", **kwargs})

    async def notify_needs_input(self, **kwargs):
        self.events.append({"type": "needs_input", **kwargs})


@pytest.fixture
def vision_model():
    return MockVisionModel()


@pytest.fixture
def retriever():
    return MockRetriever()


@pytest.fixture
def notifier():
    return MockProgressNotifier()


@pytest.mark.asyncio
async def test_vision_node_with_image(vision_model, notifier):
    """이미지가 있을 때 Vision 노드 실행."""
    node = create_vision_node(vision_model, notifier)

    state = {
        "job_id": "test-123",
        "message": "이거 어떻게 버려요?",
        "image_url": "https://example.com/pet-bottle.jpg",
    }

    result = await node(state)

    # classification_result가 저장되었는지 확인
    assert result.get("classification_result") is not None
    assert result["classification_result"]["classification"]["major_category"] == "재활용폐기물"
    assert result.get("has_image") is True

    # Vision 이벤트 발행 확인
    assert len(notifier.events) >= 2  # started, completed
    stages = [e["stage"] for e in notifier.events]
    assert "vision" in stages


@pytest.mark.asyncio
async def test_vision_node_without_image(vision_model, notifier):
    """이미지가 없을 때 Vision 노드 스킵."""
    node = create_vision_node(vision_model, notifier)

    state = {
        "job_id": "test-124",
        "message": "페트병 버리는 방법",
        "image_url": None,
    }

    result = await node(state)

    # state가 변경되지 않아야 함
    assert result.get("classification_result") is None
    assert result.get("has_image") is None

    # 이벤트가 발행되지 않아야 함
    assert len(notifier.events) == 0


@pytest.mark.asyncio
async def test_vision_to_rag_flow(vision_model, retriever, notifier):
    """Vision → RAG 통합 플로우."""
    vision_node = create_vision_node(vision_model, notifier)
    rag_node = create_rag_node(retriever, notifier)

    # Step 1: Vision 분석
    state = {
        "job_id": "test-125",
        "message": "이 쓰레기 어떻게 분류해요?",
        "image_url": "https://example.com/waste.jpg",
    }

    state = await vision_node(state)

    # Vision 결과 확인
    assert state.get("classification_result") is not None

    # Step 2: RAG 검색 (Vision 결과 활용)
    state = await rag_node(state)

    # RAG가 Vision 분류 결과를 사용했는지 확인
    assert retriever.search_called is True
    # RAG 결과 확인
    assert state.get("disposal_rules") is not None


@pytest.mark.asyncio
async def test_vision_error_handling(notifier):
    """Vision 오류 시 graceful degradation."""

    class FailingVisionModel:
        async def analyze_image(self, image_url: str, user_input: str | None = None):
            raise RuntimeError("Vision API Error")

    node = create_vision_node(FailingVisionModel(), notifier)

    state = {
        "job_id": "test-126",
        "message": "이미지 분류해줘",
        "image_url": "https://example.com/image.jpg",
    }

    result = await node(state)

    # 오류 발생해도 state 반환
    assert result.get("vision_error") is not None
    assert result.get("has_image") is True

    # 실패 이벤트 발행
    failed_events = [e for e in notifier.events if e.get("status") == "failed"]
    assert len(failed_events) >= 1


@pytest.mark.asyncio
async def test_multiple_images_classification():
    """다양한 이미지 분류 결과 테스트."""
    test_cases = [
        {
            "name": "페트병",
            "classification": {
                "major_category": "재활용폐기물",
                "middle_category": "플라스틱류",
                "minor_category": "페트병",
            },
        },
        {
            "name": "음식물",
            "classification": {
                "major_category": "음식물류폐기물",
                "middle_category": "음식물쓰레기",
                "minor_category": None,
            },
        },
        {
            "name": "건전지",
            "classification": {
                "major_category": "재활용폐기물",
                "middle_category": "전지류",
                "minor_category": "건전지",
            },
        },
    ]

    for case in test_cases:
        vision_model = MockVisionModel(
            return_value={
                "classification": case["classification"],
                "situation_tags": [],
                "confidence": 0.9,
            }
        )
        notifier = MockProgressNotifier()
        node = create_vision_node(vision_model, notifier)

        state = {
            "job_id": f"test-{case['name']}",
            "message": f"{case['name']} 분류해줘",
            "image_url": f"https://example.com/{case['name']}.jpg",
        }

        result = await node(state)

        assert result["classification_result"]["classification"] == case["classification"]
