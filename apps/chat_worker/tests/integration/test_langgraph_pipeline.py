"""LangGraph Pipeline Integration Tests.

파이프라인 전체 흐름을 테스트합니다.
실제 LLM 호출 없이 Mock으로 통합 테스트.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from chat_worker.infrastructure.orchestration.langgraph.factory import create_chat_graph


class MockLLMClient:
    """Mock LLM Client."""

    async def generate(self, prompt: str, **kwargs) -> str:
        if "intent" in prompt.lower() or "분류" in prompt.lower():
            return "waste"
        return "테스트 답변입니다."

    async def stream(self, prompt: str, **kwargs):
        for token in ["테스트", " ", "답변", "입니다", "."]:
            yield token


class MockVisionModel:
    """Mock Vision Model."""

    async def analyze_image(
        self, image_url: str, user_input: str | None = None
    ) -> dict[str, Any]:
        return {
            "classification": {
                "major_category": "재활용폐기물",
                "middle_category": "플라스틱류",
                "minor_category": "페트병",
            },
            "situation_tags": ["세척필요"],
            "confidence": 0.95,
        }


class MockRetriever:
    """Mock Retriever."""

    def search(self, category: str, subcategory: str) -> dict | None:
        return {
            "category": category,
            "subcategory": subcategory,
            "disposal_method": "깨끗이 씻어서 분리수거함에 배출",
        }

    def search_by_keyword(self, keyword: str, limit: int = 5) -> list:
        return [{"keyword": keyword, "disposal_method": "분리수거"}]


class MockProgressNotifier:
    """Mock Progress Notifier."""

    def __init__(self):
        self.events: list[dict] = []

    async def notify_stage(self, **kwargs):
        self.events.append({"type": "stage", **kwargs})

    async def notify_token(self, **kwargs):
        self.events.append({"type": "token", **kwargs})

    async def notify_needs_input(self, **kwargs):
        self.events.append({"type": "needs_input", **kwargs})


class MockCharacterClient:
    """Mock Character gRPC Client."""

    async def get_character(self, character_id: str) -> dict | None:
        return {
            "id": character_id,
            "name": "에코",
            "personality": "친근한",
        }

    async def get_random_character(self) -> dict | None:
        return {"id": "eco", "name": "에코"}


class MockLocationClient:
    """Mock Location gRPC Client."""

    async def search_recycling_centers(
        self, latitude: float, longitude: float, radius: int = 5000
    ) -> list:
        return [
            {"name": "강남 재활용센터", "distance": 500},
            {"name": "서초 재활용센터", "distance": 1200},
        ]

    async def search_zerowaste_shops(
        self, latitude: float, longitude: float, radius: int = 5000
    ) -> list:
        return [{"name": "제로웨이스트샵", "distance": 800}]


@pytest.fixture
def mock_dependencies():
    """Mock dependencies for testing."""
    return {
        "llm": MockLLMClient(),
        "vision_model": MockVisionModel(),
        "retriever": MockRetriever(),
        "event_publisher": MockProgressNotifier(),
        "character_client": MockCharacterClient(),
        "location_client": MockLocationClient(),
    }


@pytest.mark.asyncio
async def test_pipeline_text_only_waste_query(mock_dependencies):
    """텍스트만 있는 폐기물 질문 플로우 테스트."""
    graph = create_chat_graph(
        llm=mock_dependencies["llm"],
        retriever=mock_dependencies["retriever"],
        event_publisher=mock_dependencies["event_publisher"],
        vision_model=mock_dependencies["vision_model"],
        character_client=mock_dependencies["character_client"],
        location_client=mock_dependencies["location_client"],
    )

    initial_state = {
        "job_id": "test-job-001",
        "session_id": "test-session",
        "user_id": "test-user",
        "message": "페트병은 어떻게 버리나요?",
        "image_url": None,
        "user_location": None,
    }

    result = await graph.ainvoke(initial_state)

    # 결과 검증
    assert result.get("job_id") == "test-job-001"
    assert "intent" in result or "answer" in result

    # 이벤트 발행 검증
    notifier = mock_dependencies["event_publisher"]
    assert len(notifier.events) > 0
    stages = [e["stage"] for e in notifier.events if e["type"] == "stage"]
    assert "intent" in stages


@pytest.mark.asyncio
async def test_pipeline_with_image(mock_dependencies):
    """이미지가 있는 폐기물 분류 플로우 테스트."""
    graph = create_chat_graph(
        llm=mock_dependencies["llm"],
        retriever=mock_dependencies["retriever"],
        event_publisher=mock_dependencies["event_publisher"],
        vision_model=mock_dependencies["vision_model"],
        character_client=mock_dependencies["character_client"],
        location_client=mock_dependencies["location_client"],
    )

    initial_state = {
        "job_id": "test-job-002",
        "session_id": "test-session",
        "user_id": "test-user",
        "message": "이 쓰레기 어떻게 버려요?",
        "image_url": "https://example.com/image.jpg",
        "user_location": None,
    }

    result = await graph.ainvoke(initial_state)

    # Vision 결과가 state에 저장되었는지 확인
    assert result.get("classification_result") is not None or result.get("has_image")

    # Vision 이벤트 발행 검증
    notifier = mock_dependencies["event_publisher"]
    stages = [e["stage"] for e in notifier.events if e["type"] == "stage"]
    assert "vision" in stages or "intent" in stages


@pytest.mark.asyncio
async def test_pipeline_with_location(mock_dependencies):
    """위치 정보가 있는 플로우 테스트."""
    graph = create_chat_graph(
        llm=mock_dependencies["llm"],
        retriever=mock_dependencies["retriever"],
        event_publisher=mock_dependencies["event_publisher"],
        vision_model=mock_dependencies["vision_model"],
        character_client=mock_dependencies["character_client"],
        location_client=mock_dependencies["location_client"],
    )

    initial_state = {
        "job_id": "test-job-003",
        "session_id": "test-session",
        "user_id": "test-user",
        "message": "근처 재활용센터 알려줘",
        "image_url": None,
        "user_location": {"latitude": 37.5665, "longitude": 126.9780},
    }

    result = await graph.ainvoke(initial_state)

    assert result.get("job_id") == "test-job-003"


@pytest.mark.asyncio
async def test_pipeline_events_sequence(mock_dependencies):
    """이벤트 발행 순서 검증."""
    graph = create_chat_graph(
        llm=mock_dependencies["llm"],
        retriever=mock_dependencies["retriever"],
        event_publisher=mock_dependencies["event_publisher"],
        vision_model=mock_dependencies["vision_model"],
    )

    initial_state = {
        "job_id": "test-job-004",
        "session_id": "test-session",
        "user_id": "test-user",
        "message": "플라스틱 분리배출 방법",
        "image_url": None,
        "user_location": None,
    }

    await graph.ainvoke(initial_state)

    notifier = mock_dependencies["event_publisher"]
    events = notifier.events

    # 최소한 intent와 answer 이벤트가 발행되어야 함
    stage_events = [e for e in events if e["type"] == "stage"]
    assert len(stage_events) >= 2

    # 첫 번째 stage 이벤트는 intent여야 함
    first_stage = stage_events[0]["stage"]
    assert first_stage == "intent"
