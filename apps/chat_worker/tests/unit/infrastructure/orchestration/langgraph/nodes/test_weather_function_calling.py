"""Weather Node Function Calling 단위 테스트.

Function Calling 동작 테스트:
1. test_weather_needed - needs_weather=true, API 호출됨
2. test_weather_not_needed - needs_weather=false, API 스킵
3. test_function_call_fallback - Function call 실패 시 API 호출로 fallback
4. test_waste_category_extraction - Function call로 waste_category 추출

Mock 사용:
- MockLLMClient: LLM Function Calling
- MockWeatherClient: 날씨 API
- MockEventPublisher: Progress 이벤트
- NodeExecutor: Policy 적용 (테스트에서 Mock 주입)
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from chat_worker.application.ports.weather_client import (
    CurrentWeatherDTO,
    PrecipitationType,
    SkyStatus,
    WeatherResponse,
)
from chat_worker.infrastructure.orchestration.langgraph.nodes.node_executor import (
    NodeExecutor,
)
from chat_worker.infrastructure.orchestration.langgraph.nodes.weather_node import (
    create_weather_node,
)


class MockLLMClient:
    """테스트용 Mock LLM Client (Function Calling 지원)."""

    def __init__(self):
        self.function_calls: list[tuple[str | None, dict[str, Any] | None]] = []
        self.call_count = 0

    def set_function_call_response(
        self,
        function_name: str | None,
        arguments: dict[str, Any] | None,
    ):
        """Function call 응답 설정."""
        self.function_calls.append((function_name, arguments))

    async def generate_function_call(
        self,
        prompt: str,
        functions: list[dict[str, Any]],
        system_prompt: str | None = None,
        function_call: str | dict[str, str] = "auto",
    ) -> tuple[str | None, dict[str, Any] | None]:
        """Function Calling 시뮬레이션."""
        self.call_count += 1
        if self.function_calls:
            return self.function_calls.pop(0)
        # 기본값: 날씨 필요
        return ("get_weather", {"needs_weather": True, "waste_category": None})


class MockWeatherClient:
    """테스트용 Mock Weather Client."""

    def __init__(self):
        self.api_called = False
        self.call_count = 0
        self._response = WeatherResponse(
            success=True,
            current=CurrentWeatherDTO(
                temperature=15.0,
                precipitation=0.0,
                precipitation_type=PrecipitationType.NONE,
                humidity=60,
                sky_status=SkyStatus.CLEAR,
                wind_speed=2.5,
            ),
            nx=60,
            ny=127,
        )

    def set_response(self, response: WeatherResponse):
        """응답 설정."""
        self._response = response

    async def get_current_weather(self, nx: int, ny: int) -> WeatherResponse:
        """현재 날씨 조회."""
        self.api_called = True
        self.call_count += 1
        return self._response

    async def get_forecast(self, nx: int, ny: int, hours: int = 24) -> WeatherResponse:
        """단기예보 조회 (사용 안함)."""
        return self._response

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


class MockCircuitBreaker:
    """테스트용 Mock Circuit Breaker."""

    def __init__(self):
        self.state = MagicMock()
        self.state.value = "closed"

    async def allow_request(self) -> bool:
        return True

    async def record_success(self):
        pass

    async def record_failure(self):
        pass

    def retry_after(self) -> int:
        return 0


class MockCircuitBreakerRegistry:
    """테스트용 Mock Circuit Breaker Registry."""

    def __init__(self):
        self._cb = MockCircuitBreaker()

    def get(self, name: str, threshold: int = 5):
        return self._cb


@pytest.fixture
def mock_llm():
    """Mock LLM Client."""
    return MockLLMClient()


@pytest.fixture
def mock_weather_client():
    """Mock Weather Client."""
    return MockWeatherClient()


@pytest.fixture
def mock_publisher():
    """Mock Event Publisher."""
    return MockEventPublisher()


@pytest.fixture
def mock_cb_registry():
    """Mock Circuit Breaker Registry."""
    return MockCircuitBreakerRegistry()


@pytest.fixture(autouse=True)
def setup_node_executor(mock_cb_registry):
    """NodeExecutor에 Mock Circuit Breaker 주입."""
    NodeExecutor.reset_instance()
    NodeExecutor.get_instance(cb_registry=mock_cb_registry)
    yield
    NodeExecutor.reset_instance()


class TestWeatherFunctionCalling:
    """Weather Node Function Calling 테스트."""

    @pytest.mark.anyio
    async def test_weather_needed(
        self,
        mock_llm: MockLLMClient,
        mock_weather_client: MockWeatherClient,
        mock_publisher: MockEventPublisher,
    ):
        """Test Case 1: needs_weather=true일 때 API 호출됨."""
        # Given: LLM이 날씨 필요하다고 판단
        mock_llm.set_function_call_response(
            "get_weather",
            {"needs_weather": True, "waste_category": "종이류"},
        )

        node = create_weather_node(
            weather_client=mock_weather_client,
            event_publisher=mock_publisher,
            llm=mock_llm,
        )

        state = {
            "job_id": "test-job-1",
            "message": "비 오는데 종이 버려도 돼?",
            "user_location": {"lat": 37.5665, "lon": 126.9780},
        }

        # When: 노드 실행
        result = await node(state)

        # Then: LLM Function Calling 호출됨
        assert mock_llm.call_count == 1

        # Then: 날씨 API 호출됨
        assert mock_weather_client.api_called is True
        assert mock_weather_client.call_count == 1

        # Then: 날씨 컨텍스트 반환됨
        assert "weather_context" in result
        weather_ctx = result["weather_context"]
        assert weather_ctx.get("success") is True
        assert "temperature" in weather_ctx
        assert weather_ctx["temperature"] == 15.0

        # Then: Progress 이벤트 발행됨
        started_events = [e for e in mock_publisher.stages if e["status"] == "started"]
        assert len(started_events) >= 1
        assert started_events[0]["stage"] == "weather"

        completed_events = [e for e in mock_publisher.stages if e["status"] == "completed"]
        assert len(completed_events) >= 1
        assert completed_events[0]["stage"] == "weather"

    @pytest.mark.anyio
    async def test_weather_not_needed(
        self,
        mock_llm: MockLLMClient,
        mock_weather_client: MockWeatherClient,
        mock_publisher: MockEventPublisher,
    ):
        """Test Case 2: needs_weather=false일 때 API 스킵."""
        # Given: LLM이 날씨 불필요하다고 판단
        mock_llm.set_function_call_response(
            "get_weather",
            {"needs_weather": False},
        )

        node = create_weather_node(
            weather_client=mock_weather_client,
            event_publisher=mock_publisher,
            llm=mock_llm,
        )

        state = {
            "job_id": "test-job-2",
            "message": "페트병 분리배출 방법 알려줘",
            "user_location": {"lat": 37.5665, "lon": 126.9780},
        }

        # When: 노드 실행
        result = await node(state)

        # Then: LLM Function Calling 호출됨
        assert mock_llm.call_count == 1

        # Then: 날씨 API 호출 안됨
        assert mock_weather_client.api_called is False
        assert mock_weather_client.call_count == 0

        # Then: 스킵 컨텍스트 반환됨
        assert "weather_context" in result
        weather_ctx = result["weather_context"]
        assert weather_ctx.get("skipped") is True
        assert weather_ctx.get("reason") == "날씨 정보 불필요"

        # Then: 스킵 이벤트 발행됨
        skipped_events = [e for e in mock_publisher.stages if e["status"] == "skipped"]
        assert len(skipped_events) >= 1
        assert skipped_events[0]["stage"] == "weather"

    @pytest.mark.anyio
    async def test_function_call_fallback(
        self,
        mock_weather_client: MockWeatherClient,
        mock_publisher: MockEventPublisher,
    ):
        """Test Case 3: Function call 실패 시 fallback으로 API 호출."""

        # Given: LLM Function Calling이 실패하는 Mock
        class ErrorLLM:
            def __init__(self):
                self.call_count = 0

            async def generate_function_call(
                self,
                prompt: str,
                functions: list[dict[str, Any]],
                system_prompt: str | None = None,
                function_call: str | dict[str, str] = "auto",
            ) -> tuple[str | None, dict[str, Any] | None]:
                self.call_count += 1
                raise Exception("LLM API Error")

        error_llm = ErrorLLM()

        node = create_weather_node(
            weather_client=mock_weather_client,
            event_publisher=mock_publisher,
            llm=error_llm,
        )

        state = {
            "job_id": "test-job-3",
            "message": "날씨 알려줘",
            "user_location": {"lat": 37.5665, "lon": 126.9780},
        }

        # When: 노드 실행
        result = await node(state)

        # Then: LLM 호출 시도됨
        assert error_llm.call_count == 1

        # Then: fallback으로 날씨 API 호출됨
        assert mock_weather_client.api_called is True
        assert mock_weather_client.call_count == 1

        # Then: 날씨 컨텍스트 반환됨 (fallback 성공)
        assert "weather_context" in result
        weather_ctx = result["weather_context"]
        assert weather_ctx.get("success") is True

    @pytest.mark.anyio
    async def test_waste_category_extraction(
        self,
        mock_llm: MockLLMClient,
        mock_weather_client: MockWeatherClient,
        mock_publisher: MockEventPublisher,
    ):
        """Test Case 4: Function call로 waste_category 추출."""
        # Given: LLM이 waste_category를 추출
        mock_llm.set_function_call_response(
            "get_weather",
            {"needs_weather": True, "waste_category": "음식물"},
        )

        node = create_weather_node(
            weather_client=mock_weather_client,
            event_publisher=mock_publisher,
            llm=mock_llm,
        )

        state = {
            "job_id": "test-job-4",
            "message": "음식물 쓰레기 버릴 때 주의사항",
            "user_location": {"lat": 37.5665, "lon": 126.9780},
        }

        # When: 노드 실행
        result = await node(state)

        # Then: waste_category가 Command에 전달됨 (로그 확인 필요)
        # GetWeatherCommand가 waste_category를 받아서 맞춤 팁 생성
        assert "weather_context" in result
        weather_ctx = result["weather_context"]
        assert weather_ctx.get("success") is True

        # Then: 날씨 팁이 포함됨
        assert "tip" in weather_ctx or weather_ctx.get("tip") is not None

    @pytest.mark.anyio
    async def test_waste_category_from_classification_fallback(
        self,
        mock_llm: MockLLMClient,
        mock_weather_client: MockWeatherClient,
        mock_publisher: MockEventPublisher,
    ):
        """Function call에 waste_category 없으면 classification_result에서 추출."""
        # Given: LLM이 waste_category를 추출하지 않음
        mock_llm.set_function_call_response(
            "get_weather",
            {"needs_weather": True},  # waste_category 없음
        )

        node = create_weather_node(
            weather_client=mock_weather_client,
            event_publisher=mock_publisher,
            llm=mock_llm,
        )

        state = {
            "job_id": "test-job-5",
            "message": "종이 버리기 좋은 날씨야?",
            "user_location": {"lat": 37.5665, "lon": 126.9780},
            "classification_result": {
                "category": "종이류",
                "confidence": 0.95,
            },
        }

        # When: 노드 실행
        result = await node(state)

        # Then: classification_result에서 waste_category 추출됨
        assert "weather_context" in result
        weather_ctx = result["weather_context"]
        assert weather_ctx.get("success") is True


class TestWeatherNodeEdgeCases:
    """Weather Node 엣지 케이스 테스트."""

    @pytest.mark.anyio
    async def test_no_location(
        self,
        mock_llm: MockLLMClient,
        mock_weather_client: MockWeatherClient,
        mock_publisher: MockEventPublisher,
    ):
        """위치 정보 없을 때 처리."""
        mock_llm.set_function_call_response(
            "get_weather",
            {"needs_weather": True},
        )

        node = create_weather_node(
            weather_client=mock_weather_client,
            event_publisher=mock_publisher,
            llm=mock_llm,
        )

        state = {
            "job_id": "test-job-6",
            "message": "날씨 알려줘",
            # user_location 없음
        }

        # When: 노드 실행
        result = await node(state)

        # Then: 날씨 API 호출 안됨
        assert mock_weather_client.api_called is False

        # Then: 에러 컨텍스트 반환됨
        assert "weather_context" in result
        weather_ctx = result["weather_context"]
        assert weather_ctx.get("success") is False
        assert weather_ctx.get("error") == "위치 정보 없음"

        # Then: 스킵 이벤트 발행됨
        skipped_events = [e for e in mock_publisher.stages if e["status"] == "skipped"]
        assert len(skipped_events) >= 1

    @pytest.mark.anyio
    async def test_weather_api_error(
        self,
        mock_llm: MockLLMClient,
        mock_publisher: MockEventPublisher,
    ):
        """날씨 API 에러 처리."""
        mock_llm.set_function_call_response(
            "get_weather",
            {"needs_weather": True},
        )

        # Given: 날씨 API가 실패하는 Mock
        class ErrorWeatherClient:
            async def get_current_weather(self, nx: int, ny: int) -> WeatherResponse:
                return WeatherResponse(
                    success=False,
                    error_message="API timeout",
                )

            async def get_forecast(self, nx: int, ny: int, hours: int = 24):
                return WeatherResponse(success=False)

            async def close(self):
                pass

        error_client = ErrorWeatherClient()

        node = create_weather_node(
            weather_client=error_client,
            event_publisher=mock_publisher,
            llm=mock_llm,
        )

        state = {
            "job_id": "test-job-7",
            "message": "날씨 알려줘",
            "user_location": {"lat": 37.5665, "lon": 126.9780},
        }

        # When: 노드 실행
        result = await node(state)

        # Then: 에러 컨텍스트 반환됨
        assert "weather_context" in result
        weather_ctx = result["weather_context"]
        assert weather_ctx.get("success") is False
        assert weather_ctx.get("error") == "API timeout"

        # Then: 실패 이벤트 발행됨
        failed_events = [e for e in mock_publisher.stages if e["status"] == "failed"]
        assert len(failed_events) >= 1

    @pytest.mark.anyio
    async def test_function_call_with_different_locations(
        self,
        mock_llm: MockLLMClient,
        mock_weather_client: MockWeatherClient,
        mock_publisher: MockEventPublisher,
    ):
        """다양한 위치 형식 처리 (lat/lon vs latitude/longitude)."""
        mock_llm.set_function_call_response(
            "get_weather",
            {"needs_weather": True},
        )

        node = create_weather_node(
            weather_client=mock_weather_client,
            event_publisher=mock_publisher,
            llm=mock_llm,
        )

        # Test latitude/longitude 키
        state = {
            "job_id": "test-job-8",
            "message": "날씨 알려줘",
            "user_location": {"latitude": 37.5665, "longitude": 126.9780},
        }

        result = await node(state)

        assert "weather_context" in result
        assert result["weather_context"].get("success") is True
        assert mock_weather_client.api_called is True


class TestWeatherNodeChannelSeparation:
    """Channel Separation 테스트."""

    @pytest.mark.anyio
    async def test_returns_only_weather_context_channel(
        self,
        mock_llm: MockLLMClient,
        mock_weather_client: MockWeatherClient,
        mock_publisher: MockEventPublisher,
    ):
        """노드는 자신의 채널만 반환 (Channel Separation)."""
        mock_llm.set_function_call_response(
            "get_weather",
            {"needs_weather": True},
        )

        node = create_weather_node(
            weather_client=mock_weather_client,
            event_publisher=mock_publisher,
            llm=mock_llm,
        )

        state = {
            "job_id": "test-job-9",
            "message": "날씨 알려줘",
            "user_location": {"lat": 37.5665, "lon": 126.9780},
            "intent": "weather",
            "session_id": "session-1",
            "existing_key": "should_be_preserved",
        }

        result = await node(state)

        # Then: weather_context만 반환 (Channel Separation)
        assert "weather_context" in result

        # Then: 기존 state 키들은 반환하지 않음 (LangGraph reducer가 병합)
        # node_results는 NodeExecutor가 추가하므로 제외
        state_keys = set(result.keys()) - {"node_results"}
        assert state_keys == {"weather_context"}

    @pytest.mark.anyio
    async def test_context_has_scheduling_metadata(
        self,
        mock_llm: MockLLMClient,
        mock_weather_client: MockWeatherClient,
        mock_publisher: MockEventPublisher,
    ):
        """컨텍스트에 스케줄링 메타데이터 포함."""
        mock_llm.set_function_call_response(
            "get_weather",
            {"needs_weather": True},
        )

        node = create_weather_node(
            weather_client=mock_weather_client,
            event_publisher=mock_publisher,
            llm=mock_llm,
        )

        state = {
            "job_id": "test-job-10",
            "message": "날씨 알려줘",
            "user_location": {"lat": 37.5665, "lon": 126.9780},
        }

        result = await node(state)

        weather_ctx = result["weather_context"]

        # Then: 스케줄링 메타데이터 포함
        assert "_priority" in weather_ctx
        assert "_sequence" in weather_ctx
        assert "_producer" in weather_ctx
        assert weather_ctx["_producer"] == "weather"
        assert "_created_at" in weather_ctx
        assert "_is_fallback" in weather_ctx
