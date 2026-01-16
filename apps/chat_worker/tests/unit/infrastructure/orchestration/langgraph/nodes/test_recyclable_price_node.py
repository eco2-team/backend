"""Recyclable Price Node 단위 테스트.

LangGraph 어댑터(Node) 테스트.

테스트 대상:
- state → input DTO 변환
- Command 호출
- output → state 변환
- Progress 이벤트 발행
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from chat_worker.application.commands.search_recyclable_price_command import (
    SearchRecyclablePriceOutput,
)
from chat_worker.application.ports.recyclable_price_client import (
    RecyclableCategory,
    RecyclablePriceDTO,
    RecyclablePriceSearchResponse,
    RecyclableRegion,
)
from chat_worker.infrastructure.orchestration.langgraph.nodes.recyclable_price_node import (
    create_recyclable_price_node,
)


class MockRecyclablePriceClient:
    """테스트용 Mock Price Client."""

    def __init__(self):
        self._response = RecyclablePriceSearchResponse(
            items=[
                RecyclablePriceDTO(
                    item_code="metal_aluminum_can",
                    item_name="알루미늄캔",
                    category=RecyclableCategory.METAL,
                    price_per_kg=1200,
                    survey_date="2025-01",
                ),
            ],
            query="캔",
            survey_date="2025-01",
            total_count=1,
        )

    async def search_price(self, item_name: str, region=None):
        return self._response

    async def get_category_prices(self, category, region=None):
        return self._response

    async def get_all_prices(self, region=None):
        return self._response

    async def get_price_trend(self, item_name, region=None, months=6):
        return None

    async def close(self):
        pass


class MockEventPublisher:
    """테스트용 Mock Event Publisher."""

    def __init__(self):
        self.stages: list[dict] = []

    async def notify_stage(
        self,
        task_id: str,
        stage: str,
        status: str,
        progress: int | None = None,
        result: dict[str, Any] | None = None,
        message: str | None = None,
    ):
        self.stages.append(
            {
                "task_id": task_id,
                "stage": stage,
                "status": status,
                "progress": progress,
                "result": result,
                "message": message,
            }
        )
        return "event-id"


class TestRecyclablePriceNode:
    """Recyclable Price Node 테스트 스위트."""

    @pytest.fixture
    def mock_client(self) -> MockRecyclablePriceClient:
        """Mock Price Client."""
        return MockRecyclablePriceClient()

    @pytest.fixture
    def mock_publisher(self) -> MockEventPublisher:
        """Mock Event Publisher."""
        return MockEventPublisher()

    @pytest.fixture
    def node(
        self,
        mock_client: MockRecyclablePriceClient,
        mock_publisher: MockEventPublisher,
    ):
        """테스트용 Node."""
        return create_recyclable_price_node(mock_client, mock_publisher)

    # ==========================================================
    # Basic Execution Tests
    # ==========================================================

    @pytest.mark.anyio
    async def test_node_success(
        self,
        node,
        mock_publisher: MockEventPublisher,
    ):
        """성공 실행."""
        state = {
            "job_id": "job-123",
            "message": "캔 얼마야?",
            "recyclable_item": "캔",
        }

        result = await node(state)

        assert "recyclable_price_context" in result
        assert result["recyclable_price_context"] is not None
        assert result.get("recyclable_price_error") is None

    @pytest.mark.anyio
    async def test_node_extracts_item_from_message(
        self,
        node,
    ):
        """메시지에서 품목명 추출."""
        state = {
            "job_id": "job-456",
            "message": "페트병 시세 알려줘",
            # recyclable_item 없음 → message에서 추출
        }

        result = await node(state)

        # Command가 message에서 추출
        assert "recyclable_price_context" in result

    @pytest.mark.anyio
    async def test_node_uses_explicit_item(
        self,
        mock_client: MockRecyclablePriceClient,
        mock_publisher: MockEventPublisher,
    ):
        """명시적 품목명 우선 사용."""
        mock_client.search_price = AsyncMock(
            return_value=RecyclablePriceSearchResponse(
                items=[
                    RecyclablePriceDTO(
                        item_code="plastic_pet",
                        item_name="PET",
                        category=RecyclableCategory.PLASTIC,
                        price_per_kg=350,
                    ),
                ],
                query="페트",
                total_count=1,
            )
        )

        node = create_recyclable_price_node(mock_client, mock_publisher)

        state = {
            "job_id": "job-789",
            "message": "캔 얼마야?",  # message에는 "캔"
            "recyclable_item": "페트",  # 명시적으로 "페트" 지정
        }

        await node(state)

        # 명시적 item_name이 우선
        call_kwargs = mock_client.search_price.call_args.kwargs
        assert call_kwargs["item_name"] == "페트"

    # ==========================================================
    # State Transformation Tests
    # ==========================================================

    @pytest.mark.anyio
    async def test_node_passes_category(
        self,
        mock_client: MockRecyclablePriceClient,
        mock_publisher: MockEventPublisher,
    ):
        """카테고리 전달."""
        mock_client.get_category_prices = AsyncMock(
            return_value=RecyclablePriceSearchResponse(
                items=[],
                query="metal",
                total_count=0,
            )
        )

        node = create_recyclable_price_node(mock_client, mock_publisher)

        state = {
            "job_id": "job-cat",
            "message": "폐금속 시세",
            "recyclable_category": RecyclableCategory.METAL,
        }

        await node(state)

        mock_client.get_category_prices.assert_called_once()

    @pytest.mark.anyio
    async def test_node_passes_region(
        self,
        mock_client: MockRecyclablePriceClient,
        mock_publisher: MockEventPublisher,
    ):
        """권역 전달."""
        mock_client.search_price = AsyncMock(
            return_value=RecyclablePriceSearchResponse(
                items=[],
                query="캔",
                total_count=0,
            )
        )

        node = create_recyclable_price_node(mock_client, mock_publisher)

        state = {
            "job_id": "job-region",
            "message": "캔 시세",
            "recyclable_item": "캔",
            "recyclable_region": RecyclableRegion.CAPITAL,
        }

        await node(state)

        call_kwargs = mock_client.search_price.call_args.kwargs
        assert call_kwargs["region"] == RecyclableRegion.CAPITAL

    @pytest.mark.anyio
    async def test_node_returns_context_in_state(
        self,
        node,
    ):
        """결과 컨텍스트 상태에 포함."""
        state = {
            "job_id": "job-ctx",
            "message": "캔 시세",
            "recyclable_item": "캔",
        }

        result = await node(state)

        context = result["recyclable_price_context"]
        assert context is not None
        assert context.get("type") == "recyclable_prices"
        assert "items" in context
        assert "context" in context  # LLM context 문자열

    # ==========================================================
    # Progress Event Tests
    # ==========================================================

    @pytest.mark.anyio
    async def test_node_publishes_started_event(
        self,
        node,
        mock_publisher: MockEventPublisher,
    ):
        """시작 이벤트 발행."""
        state = {
            "job_id": "job-event",
            "message": "캔 시세",
            "recyclable_item": "캔",
        }

        await node(state)

        started_events = [e for e in mock_publisher.stages if e["status"] == "started"]
        assert len(started_events) >= 1
        assert started_events[0]["stage"] == "recyclable_price"

    @pytest.mark.anyio
    async def test_node_publishes_completed_event(
        self,
        node,
        mock_publisher: MockEventPublisher,
    ):
        """완료 이벤트 발행."""
        state = {
            "job_id": "job-complete",
            "message": "캔 시세",
            "recyclable_item": "캔",
        }

        await node(state)

        completed_events = [
            e for e in mock_publisher.stages if e["status"] == "completed"
        ]
        assert len(completed_events) >= 1
        completed = completed_events[0]
        assert completed["stage"] == "recyclable_price"
        assert completed["result"]["found"] is True
        assert completed["result"]["count"] == 1

    @pytest.mark.anyio
    async def test_node_progress_message_on_found(
        self,
        node,
        mock_publisher: MockEventPublisher,
    ):
        """결과 있을 때 메시지."""
        state = {
            "job_id": "job-msg",
            "message": "캔 시세",
            "recyclable_item": "캔",
        }

        await node(state)

        completed = [e for e in mock_publisher.stages if e["status"] == "completed"][0]
        assert "품목의 시세를 찾았어요" in completed["message"]

    # ==========================================================
    # Error Handling Tests
    # ==========================================================

    @pytest.mark.anyio
    async def test_node_handles_client_error(
        self,
        mock_publisher: MockEventPublisher,
    ):
        """클라이언트 에러 처리."""

        class ErrorClient:
            async def search_price(self, item_name, region=None):
                raise Exception("Client Error")

            async def get_category_prices(self, category, region=None):
                raise Exception("Client Error")

            async def get_all_prices(self, region=None):
                raise Exception("Client Error")

            async def get_price_trend(self, item_name, region=None, months=6):
                return None

        node = create_recyclable_price_node(ErrorClient(), mock_publisher)

        state = {
            "job_id": "job-error",
            "message": "캔 시세",
            "recyclable_item": "캔",
        }

        result = await node(state)

        # 에러 상태 반환
        assert result.get("recyclable_price_error") is not None
        assert result["recyclable_price_context"]["type"] == "error"

        # 실패 이벤트 발행
        failed_events = [e for e in mock_publisher.stages if e["status"] == "failed"]
        assert len(failed_events) >= 1

    @pytest.mark.anyio
    async def test_node_handles_not_found(
        self,
        mock_client: MockRecyclablePriceClient,
        mock_publisher: MockEventPublisher,
    ):
        """검색 결과 없음 처리."""
        mock_client.search_price = AsyncMock(
            return_value=RecyclablePriceSearchResponse(
                items=[],
                query="없는품목",
                total_count=0,
            )
        )

        node = create_recyclable_price_node(mock_client, mock_publisher)

        state = {
            "job_id": "job-notfound",
            "message": "없는품목 시세",
            "recyclable_item": "없는품목",
        }

        result = await node(state)

        context = result["recyclable_price_context"]
        assert context["type"] == "not_found"

    @pytest.mark.anyio
    async def test_node_handles_no_item(
        self,
        node,
        mock_publisher: MockEventPublisher,
    ):
        """품목 없을 때 안내 메시지."""
        state = {
            "job_id": "job-noitem",
            "message": "안녕하세요",  # 품목 키워드 없음
            # recyclable_item 없음
        }

        result = await node(state)

        context = result["recyclable_price_context"]
        assert context["type"] == "guide"

    # ==========================================================
    # State Preservation Tests
    # ==========================================================

    @pytest.mark.anyio
    async def test_node_preserves_existing_state(
        self,
        node,
    ):
        """기존 state 보존."""
        state = {
            "job_id": "job-preserve",
            "message": "캔 시세",
            "recyclable_item": "캔",
            "intent": "recyclable_price",
            "session_id": "session-1",
            "existing_key": "should_be_preserved",
        }

        result = await node(state)

        # 기존 키들 보존
        assert result["job_id"] == "job-preserve"
        assert result["intent"] == "recyclable_price"
        assert result["session_id"] == "session-1"
        assert result["existing_key"] == "should_be_preserved"
        # 새 키 추가
        assert "recyclable_price_context" in result
