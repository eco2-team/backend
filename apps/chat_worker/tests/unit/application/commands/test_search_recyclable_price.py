"""SearchRecyclablePriceCommand 단위 테스트.

Command(UseCase) 레이어 테스트.

테스트 대상:
- Port 호출 오케스트레이션
- 품목명 추출 위임 (Service)
- 에러 처리
- 이벤트 생성
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from chat_worker.application.commands.search_recyclable_price_command import (
    SearchRecyclablePriceCommand,
    SearchRecyclablePriceInput,
    SearchRecyclablePriceOutput,
)
from chat_worker.application.ports.recyclable_price_client import (
    RecyclableCategory,
    RecyclablePriceDTO,
    RecyclablePriceSearchResponse,
    RecyclableRegion,
)


class MockRecyclablePriceClient:
    """Mock RecyclablePriceClientPort."""

    def __init__(
        self,
        search_response: RecyclablePriceSearchResponse | None = None,
        category_response: RecyclablePriceSearchResponse | None = None,
        raise_error: bool = False,
    ):
        default_items = [
            RecyclablePriceDTO(
                item_code="metal_aluminum_can",
                item_name="알루미늄캔",
                category=RecyclableCategory.METAL,
                price_per_kg=1200,
                survey_date="2025-01",
            ),
        ]
        self._search_response = search_response or RecyclablePriceSearchResponse(
            items=default_items,
            query="캔",
            survey_date="2025-01",
            total_count=1,
        )
        self._category_response = category_response or RecyclablePriceSearchResponse(
            items=default_items,
            query="metal",
            survey_date="2025-01",
            total_count=1,
        )
        self._raise_error = raise_error

        # Mock 메서드 설정
        if raise_error:
            self.search_price = AsyncMock(side_effect=Exception("Client Error"))
            self.get_category_prices = AsyncMock(side_effect=Exception("Client Error"))
        else:
            self.search_price = AsyncMock(return_value=self._search_response)
            self.get_category_prices = AsyncMock(return_value=self._category_response)

        self.get_all_prices = AsyncMock(return_value=self._search_response)
        self.get_price_trend = AsyncMock(return_value=None)


class TestSearchRecyclablePriceCommand:
    """SearchRecyclablePriceCommand 테스트 스위트."""

    @pytest.fixture
    def mock_client(self) -> MockRecyclablePriceClient:
        """Mock Price Client."""
        return MockRecyclablePriceClient()

    @pytest.fixture
    def command(
        self, mock_client: MockRecyclablePriceClient
    ) -> SearchRecyclablePriceCommand:
        """테스트용 Command."""
        return SearchRecyclablePriceCommand(price_client=mock_client)

    @pytest.fixture
    def sample_input(self) -> SearchRecyclablePriceInput:
        """샘플 입력."""
        return SearchRecyclablePriceInput(
            job_id="job-123",
            item_name="알루미늄캔",
        )

    # ==========================================================
    # Basic Execution Tests
    # ==========================================================

    @pytest.mark.anyio
    async def test_execute_success(
        self,
        command: SearchRecyclablePriceCommand,
        mock_client: MockRecyclablePriceClient,
        sample_input: SearchRecyclablePriceInput,
    ):
        """성공 실행."""
        result = await command.execute(sample_input)

        assert result.success is True
        assert result.error_message is None
        assert result.price_context is not None
        mock_client.search_price.assert_called_once()

    @pytest.mark.anyio
    async def test_execute_with_category(
        self,
        command: SearchRecyclablePriceCommand,
        mock_client: MockRecyclablePriceClient,
    ):
        """카테고리 검색."""
        input_dto = SearchRecyclablePriceInput(
            job_id="job-456",
            category=RecyclableCategory.METAL,
        )

        result = await command.execute(input_dto)

        assert result.success is True
        mock_client.get_category_prices.assert_called_once()
        mock_client.search_price.assert_not_called()

    @pytest.mark.anyio
    async def test_execute_with_region(
        self,
        command: SearchRecyclablePriceCommand,
        mock_client: MockRecyclablePriceClient,
    ):
        """권역 지정 검색."""
        input_dto = SearchRecyclablePriceInput(
            job_id="job-789",
            item_name="알루미늄캔",
            region=RecyclableRegion.CAPITAL,
        )

        await command.execute(input_dto)

        call_kwargs = mock_client.search_price.call_args.kwargs
        assert call_kwargs["region"] == RecyclableRegion.CAPITAL

    # ==========================================================
    # Item Name Extraction Tests
    # ==========================================================

    @pytest.mark.anyio
    async def test_execute_extract_item_from_message(
        self,
        command: SearchRecyclablePriceCommand,
        mock_client: MockRecyclablePriceClient,
    ):
        """메시지에서 품목명 추출."""
        input_dto = SearchRecyclablePriceInput(
            job_id="job-extract",
            message="캔 한 개 얼마예요?",
        )

        result = await command.execute(input_dto)

        assert result.success is True
        assert "item_extracted_from_message" in result.events
        mock_client.search_price.assert_called_once()
        call_kwargs = mock_client.search_price.call_args.kwargs
        assert call_kwargs["item_name"] == "캔"

    @pytest.mark.anyio
    async def test_execute_no_item_returns_guide(
        self,
        command: SearchRecyclablePriceCommand,
        mock_client: MockRecyclablePriceClient,
    ):
        """품목명 없으면 안내 메시지 반환."""
        input_dto = SearchRecyclablePriceInput(
            job_id="job-noitem",
            message="안녕하세요",  # 품목명 키워드 없음
        )

        result = await command.execute(input_dto)

        assert result.success is True
        assert result.price_context["type"] == "guide"
        assert "no_item_specified" in result.events
        mock_client.search_price.assert_not_called()

    # ==========================================================
    # Error Handling Tests
    # ==========================================================

    @pytest.mark.anyio
    async def test_execute_client_error(self):
        """클라이언트 에러 처리."""
        error_client = MockRecyclablePriceClient(raise_error=True)
        command = SearchRecyclablePriceCommand(price_client=error_client)

        input_dto = SearchRecyclablePriceInput(
            job_id="job-error",
            item_name="알루미늄캔",
        )

        result = await command.execute(input_dto)

        assert result.success is False
        assert result.error_message is not None
        assert "price_search_error" in result.events
        assert result.price_context["type"] == "error"

    @pytest.mark.anyio
    async def test_execute_not_found(
        self,
        mock_client: MockRecyclablePriceClient,
    ):
        """검색 결과 없음."""
        # 빈 결과 반환하도록 설정
        empty_response = RecyclablePriceSearchResponse(
            items=[],
            query="없는품목",
            total_count=0,
        )
        mock_client.search_price.return_value = empty_response

        command = SearchRecyclablePriceCommand(price_client=mock_client)
        input_dto = SearchRecyclablePriceInput(
            job_id="job-notfound",
            item_name="없는품목",
        )

        result = await command.execute(input_dto)

        assert result.success is True
        assert result.price_context["type"] == "not_found"
        assert "no_results" in result.events

    # ==========================================================
    # Events Tests
    # ==========================================================

    @pytest.mark.anyio
    async def test_execute_events_item_searched(
        self,
        command: SearchRecyclablePriceCommand,
        sample_input: SearchRecyclablePriceInput,
    ):
        """품목 검색 시 이벤트."""
        result = await command.execute(sample_input)

        assert "item_price_searched" in result.events
        assert "results_found" in result.events

    @pytest.mark.anyio
    async def test_execute_events_category_fetched(
        self,
        command: SearchRecyclablePriceCommand,
    ):
        """카테고리 검색 시 이벤트."""
        input_dto = SearchRecyclablePriceInput(
            job_id="job-cat",
            category=RecyclableCategory.PLASTIC,
        )

        result = await command.execute(input_dto)

        assert "category_prices_fetched" in result.events

    # ==========================================================
    # Output Context Tests
    # ==========================================================

    @pytest.mark.anyio
    async def test_execute_output_context_structure(
        self,
        command: SearchRecyclablePriceCommand,
        sample_input: SearchRecyclablePriceInput,
    ):
        """출력 컨텍스트 구조."""
        result = await command.execute(sample_input)

        context = result.price_context
        assert context is not None
        assert context["type"] == "recyclable_prices"
        assert "items" in context
        assert "count" in context
        assert "context" in context  # LLM context 문자열

    @pytest.mark.anyio
    async def test_execute_output_contains_context_string(
        self,
        command: SearchRecyclablePriceCommand,
        sample_input: SearchRecyclablePriceInput,
    ):
        """출력에 context 문자열 포함."""
        result = await command.execute(sample_input)

        context_str = result.price_context.get("context", "")
        assert "재활용자원 시세 정보" in context_str
        assert "알루미늄캔" in context_str


class TestSearchRecyclablePriceInputOutput:
    """Input/Output DTO 테스트."""

    def test_input_defaults(self):
        """입력 기본값."""
        input_dto = SearchRecyclablePriceInput(job_id="job-1")

        assert input_dto.item_name is None
        assert input_dto.category is None
        assert input_dto.region is None
        assert input_dto.message == ""

    def test_output_defaults(self):
        """출력 기본값."""
        output = SearchRecyclablePriceOutput(success=True)

        assert output.price_context is None
        assert output.error_message is None
        assert output.events == []

    def test_output_with_events(self):
        """출력 이벤트."""
        output = SearchRecyclablePriceOutput(
            success=True,
            events=["event1", "event2"],
        )

        assert len(output.events) == 2
        assert "event1" in output.events
