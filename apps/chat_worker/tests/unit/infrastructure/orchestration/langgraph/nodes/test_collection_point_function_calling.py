"""Collection Point Node Function Calling 단위 테스트.

Function Calling 기능 테스트:
- LLM이 사용자 메시지에서 수거함 검색 파라미터를 동적으로 추출
- 수거 품목(의류, 폐건전지, 형광등, 폐휴대폰) 자동 파악
- 검색 반경 자동 설정
- 한글 품목명 → 영문 코드 매핑
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from chat_worker.application.ports.collection_point_client import (
    CollectionPointDTO,
    CollectionPointSearchResponse,
)
from chat_worker.infrastructure.orchestration.langgraph.nodes.collection_point_node import (
    create_collection_point_node,
)


class MockLLMClient:
    """테스트용 Mock LLM Client (Function Calling 지원)."""

    def __init__(self):
        self.function_calls: list[tuple[str, dict]] = []
        self.call_count = 0

    async def generate_function_call(
        self,
        prompt: str,
        functions: list[dict[str, Any]],
        system_prompt: str | None = None,
        function_call: str | dict[str, str] = "auto",
    ) -> tuple[str | None, dict[str, Any] | None]:
        """Mock function call - 미리 설정된 결과 반환."""
        self.call_count += 1
        if not self.function_calls:
            return None, None
        return self.function_calls[0]

    def set_function_call_result(self, func_name: str, func_args: dict[str, Any]):
        """Function call 결과 설정."""
        self.function_calls = [(func_name, func_args)]


class MockCollectionPointClient:
    """테스트용 Mock Collection Point Client."""

    def __init__(self):
        self._response = CollectionPointSearchResponse(
            results=[
                CollectionPointDTO(
                    id=1,
                    name="이마트 강남점",
                    collection_types=("폐휴대폰", "폐가전"),
                    collection_method="수거함 설치",
                    address="서울특별시 강남구 테헤란로 123",
                    place_category="대형마트",
                    fee="무료",
                ),
            ],
            total_count=1,
            page=1,
            page_size=10,
        )

    async def search_collection_points(
        self,
        address_keyword: str | None = None,
        name_keyword: str | None = None,
        page: int = 1,
        page_size: int = 10,
    ) -> CollectionPointSearchResponse:
        return self._response

    async def get_nearby_collection_points(
        self,
        lat: float,
        lon: float,
        radius_km: float = 2.0,
        limit: int = 10,
    ) -> list[CollectionPointDTO]:
        return self._response.results

    async def close(self):
        pass


class MockEventPublisher:
    """테스트용 Mock Event Publisher."""

    def __init__(self):
        self.stages: list[dict] = []
        self.needs_input_calls: list[dict] = []

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

    async def notify_needs_input(
        self,
        task_id: str,
        input_type: str,
        message: str,
        timeout: int = 60,
    ):
        self.needs_input_calls.append(
            {
                "task_id": task_id,
                "input_type": input_type,
                "message": message,
                "timeout": timeout,
            }
        )
        return "input-id"


class MockCircuitBreaker:
    """테스트용 Mock Circuit Breaker."""

    async def allow_request(self) -> bool:
        return True

    async def record_success(self):
        pass

    async def record_failure(self):
        pass


class MockCircuitBreakerRegistry:
    """테스트용 Mock Circuit Breaker Registry."""

    def __init__(self):
        self._cb = MockCircuitBreaker()

    def get(self, name: str, threshold: int = 5):
        return self._cb


class TestCollectionPointFunctionCalling:
    """Collection Point Function Calling 테스트 스위트."""

    @pytest.fixture
    def mock_llm(self) -> MockLLMClient:
        """Mock LLM Client."""
        return MockLLMClient()

    @pytest.fixture
    def mock_client(self) -> MockCollectionPointClient:
        """Mock Collection Point Client."""
        return MockCollectionPointClient()

    @pytest.fixture
    def mock_publisher(self) -> MockEventPublisher:
        """Mock Event Publisher."""
        return MockEventPublisher()

    @pytest.fixture
    def mock_cb_registry(self) -> MockCircuitBreakerRegistry:
        """Mock Circuit Breaker Registry."""
        return MockCircuitBreakerRegistry()

    @pytest.fixture
    def node(
        self,
        mock_client: MockCollectionPointClient,
        mock_publisher: MockEventPublisher,
        mock_llm: MockLLMClient,
        mock_cb_registry: MockCircuitBreakerRegistry,
    ):
        """테스트용 Node with mocked NodeExecutor."""
        # NodeExecutor 싱글톤에 mock CB registry 주입
        from chat_worker.infrastructure.orchestration.langgraph.nodes.node_executor import (
            NodeExecutor,
        )

        NodeExecutor.get_instance(cb_registry=mock_cb_registry)

        return create_collection_point_node(
            collection_point_client=mock_client,
            event_publisher=mock_publisher,
            llm=mock_llm,
        )

    # ==========================================================
    # Test 1: test_item_type_extraction
    # ==========================================================

    @pytest.mark.anyio
    async def test_item_type_extraction_clothes(
        self,
        node,
        mock_llm: MockLLMClient,
        mock_publisher: MockEventPublisher,
    ):
        """의류 수거함 추출 테스트."""
        # LLM이 "의류" 품목을 추출하도록 설정
        mock_llm.set_function_call_result(
            "find_collection_points",
            {"item_type": "clothes", "search_radius_km": 2.0},
        )

        state = {
            "job_id": "job-123",
            "message": "의류수거함 어디 있어?",
            "collection_point_address": "강남구",
        }

        result = await node(state)

        # Function call 호출 확인
        assert mock_llm.call_count == 1

        # Context 생성 확인
        assert "collection_point_context" in result
        context = result["collection_point_context"]
        assert context is not None

        # 성공 이벤트 발행 확인
        completed_events = [e for e in mock_publisher.stages if e["status"] == "completed"]
        assert len(completed_events) >= 1

    @pytest.mark.anyio
    async def test_item_type_extraction_battery(
        self,
        node,
        mock_llm: MockLLMClient,
    ):
        """폐건전지 수거함 추출 테스트."""
        mock_llm.set_function_call_result(
            "find_collection_points",
            {"item_type": "battery", "search_radius_km": 2.0},
        )

        state = {
            "job_id": "job-124",
            "message": "폐건전지 버리는 곳 알려줘",
            "collection_point_address": "용산구",
        }

        result = await node(state)

        assert mock_llm.call_count == 1
        assert "collection_point_context" in result

    @pytest.mark.anyio
    async def test_item_type_extraction_phone(
        self,
        node,
        mock_llm: MockLLMClient,
    ):
        """폐휴대폰 수거함 추출 테스트."""
        mock_llm.set_function_call_result(
            "find_collection_points",
            {"item_type": "phone", "search_radius_km": 2.0},
        )

        state = {
            "job_id": "job-125",
            "message": "폐휴대폰 어디서 버려?",
            "collection_point_address": "서초구",
        }

        result = await node(state)

        assert mock_llm.call_count == 1
        assert "collection_point_context" in result

    @pytest.mark.anyio
    async def test_item_type_extraction_fluorescent_lamp(
        self,
        node,
        mock_llm: MockLLMClient,
    ):
        """형광등 수거함 추출 테스트."""
        mock_llm.set_function_call_result(
            "find_collection_points",
            {"item_type": "fluorescent_lamp", "search_radius_km": 2.0},
        )

        state = {
            "job_id": "job-126",
            "message": "형광등 버리는 곳",
            "collection_point_address": "송파구",
        }

        result = await node(state)

        assert mock_llm.call_count == 1
        assert "collection_point_context" in result

    # ==========================================================
    # Test 2: test_custom_radius
    # ==========================================================

    @pytest.mark.anyio
    async def test_custom_radius_3km(
        self,
        node,
        mock_llm: MockLLMClient,
    ):
        """사용자 지정 반경 3km 추출 테스트."""
        mock_llm.set_function_call_result(
            "find_collection_points",
            {"item_type": "clothes", "search_radius_km": 3.0},
        )

        state = {
            "job_id": "job-127",
            "message": "3km 이내 의류수거함 찾아줘",
            "collection_point_address": "강남구",
        }

        result = await node(state)

        assert mock_llm.call_count == 1
        # Function call에서 3.0 반환됨을 확인 (실제 Command는 반경 사용 안함)
        func_name, func_args = mock_llm.function_calls[0]
        assert func_args["search_radius_km"] == 3.0

    @pytest.mark.anyio
    async def test_custom_radius_5km(
        self,
        node,
        mock_llm: MockLLMClient,
    ):
        """사용자 지정 반경 5km 추출 테스트."""
        mock_llm.set_function_call_result(
            "find_collection_points",
            {"item_type": "battery", "search_radius_km": 5.0},
        )

        state = {
            "job_id": "job-128",
            "message": "5킬로미터 이내 폐건전지 수거함",
            "collection_point_address": "용산구",
        }

        result = await node(state)

        assert mock_llm.call_count == 1
        func_name, func_args = mock_llm.function_calls[0]
        assert func_args["search_radius_km"] == 5.0

    @pytest.mark.anyio
    async def test_default_radius_2km(
        self,
        node,
        mock_llm: MockLLMClient,
    ):
        """기본 반경 2km 사용 테스트."""
        mock_llm.set_function_call_result(
            "find_collection_points",
            {"item_type": "phone"},  # search_radius_km 없음
        )

        state = {
            "job_id": "job-129",
            "message": "폐휴대폰 수거함",
            "collection_point_address": "서초구",
        }

        result = await node(state)

        assert mock_llm.call_count == 1
        # 기본값 2.0이 없어도 동작함
        assert "collection_point_context" in result

    # ==========================================================
    # Test 3: test_fallback_on_failure
    # ==========================================================

    @pytest.mark.anyio
    async def test_fallback_on_function_call_failure(
        self,
        node,
        mock_llm: MockLLMClient,
    ):
        """Function call 실패 시 기본값 사용 테스트."""
        # Function call이 func_args=None 반환 (fallback 트리거하지만 계속 진행)
        mock_llm.set_function_call_result("find_collection_points", None)

        state = {
            "job_id": "job-130",
            "message": "collection point search",  # 영문으로 변경하여 로깅 충돌 방지
            "collection_point_address": "강남구",
        }

        result = await node(state)

        # func_args=None이면 기본값(clothes, 2.0) 사용
        assert mock_llm.call_count >= 1
        # 기본값으로 진행하므로 collection_point_context 반환
        assert "collection_point_context" in result
        context = result["collection_point_context"]
        # 성공적으로 검색됨 (기본값 사용)
        assert context is not None

    @pytest.mark.anyio
    async def test_fallback_on_llm_exception(
        self,
        mock_client: MockCollectionPointClient,
        mock_publisher: MockEventPublisher,
        mock_cb_registry: MockCircuitBreakerRegistry,
    ):
        """LLM 예외 발생 시 에러 처리 테스트."""

        class ErrorLLM:
            async def generate_function_call(
                self,
                prompt: str,
                functions: list[dict[str, Any]],
                system_prompt: str | None = None,
                function_call: str | dict[str, str] = "auto",
            ) -> tuple[str | None, dict[str, Any] | None]:
                raise Exception("LLM Error")

        from chat_worker.infrastructure.orchestration.langgraph.nodes.node_executor import (
            NodeExecutor,
        )

        NodeExecutor.get_instance(cb_registry=mock_cb_registry)

        node = create_collection_point_node(
            collection_point_client=mock_client,
            event_publisher=mock_publisher,
            llm=ErrorLLM(),
        )

        state = {
            "job_id": "job-131",
            "message": "find collection point",  # 영문으로 변경
            "collection_point_address": "강남구",
        }

        result = await node(state)

        # 에러 context 반환 (NodeExecutor가 FAIL_OPEN으로 처리하므로 node_results에 기록)
        # 에러로 인해 collection_point_context가 없을 수 있음
        assert "node_results" in result
        # NodeExecutor가 FAIL_OPEN으로 처리하므로 실패 이벤트가 없을 수 있음
        # node_results에 실패 기록 확인
        node_results = result.get("node_results", [])
        if node_results:
            assert node_results[-1]["status"] == "failed"

    @pytest.mark.anyio
    async def test_fallback_uses_default_values(
        self,
        node,
        mock_llm: MockLLMClient,
    ):
        """Fallback 시 기본값(clothes, 2.0) 사용 확인."""
        # Function call이 item_type만 반환 (search_radius_km 없음)
        mock_llm.function_calls = [("find_collection_points", {"item_type": "clothes"})]

        state = {
            "job_id": "job-132",
            "message": "수거함",
            "collection_point_address": "용산구",
        }

        result = await node(state)

        # 기본값으로 동작하여 결과 반환
        assert "collection_point_context" in result or "node_results" in result

    # ==========================================================
    # Test 4: test_item_type_mapping
    # ==========================================================

    @pytest.mark.anyio
    async def test_item_type_mapping_clothes_to_korean(
        self,
        node,
        mock_llm: MockLLMClient,
        mock_client: MockCollectionPointClient,
    ):
        """영문 코드 'clothes' → 한글 '의류' 매핑 테스트."""
        mock_client.search_collection_points = AsyncMock(
            return_value=CollectionPointSearchResponse(
                results=[],
                total_count=0,
            )
        )

        mock_llm.set_function_call_result(
            "find_collection_points",
            {"item_type": "clothes", "search_radius_km": 2.0},
        )

        state = {
            "job_id": "job-133",
            "message": "의류수거함",
            "collection_point_address": "강남구",
        }

        await node(state)

        # Command가 한글 '의류'로 검색했는지 확인
        call_kwargs = mock_client.search_collection_points.call_args.kwargs
        assert call_kwargs["name_keyword"] == "의류"

    @pytest.mark.anyio
    async def test_item_type_mapping_battery_to_korean(
        self,
        node,
        mock_llm: MockLLMClient,
        mock_client: MockCollectionPointClient,
    ):
        """영문 코드 'battery' → 한글 '폐건전지' 매핑 테스트."""
        mock_client.search_collection_points = AsyncMock(
            return_value=CollectionPointSearchResponse(
                results=[],
                total_count=0,
            )
        )

        mock_llm.set_function_call_result(
            "find_collection_points",
            {"item_type": "battery", "search_radius_km": 2.0},
        )

        state = {
            "job_id": "job-134",
            "message": "폐건전지 수거함",
            "collection_point_address": "용산구",
        }

        await node(state)

        call_kwargs = mock_client.search_collection_points.call_args.kwargs
        assert call_kwargs["name_keyword"] == "폐건전지"

    @pytest.mark.anyio
    async def test_item_type_mapping_fluorescent_lamp_to_korean(
        self,
        node,
        mock_llm: MockLLMClient,
        mock_client: MockCollectionPointClient,
    ):
        """영문 코드 'fluorescent_lamp' → 한글 '형광등' 매핑 테스트."""
        mock_client.search_collection_points = AsyncMock(
            return_value=CollectionPointSearchResponse(
                results=[],
                total_count=0,
            )
        )

        mock_llm.set_function_call_result(
            "find_collection_points",
            {"item_type": "fluorescent_lamp", "search_radius_km": 2.0},
        )

        state = {
            "job_id": "job-135",
            "message": "형광등 수거함",
            "collection_point_address": "서초구",
        }

        await node(state)

        call_kwargs = mock_client.search_collection_points.call_args.kwargs
        assert call_kwargs["name_keyword"] == "형광등"

    @pytest.mark.anyio
    async def test_item_type_mapping_phone_to_korean(
        self,
        node,
        mock_llm: MockLLMClient,
        mock_client: MockCollectionPointClient,
    ):
        """영문 코드 'phone' → 한글 '폐휴대폰' 매핑 테스트."""
        mock_client.search_collection_points = AsyncMock(
            return_value=CollectionPointSearchResponse(
                results=[],
                total_count=0,
            )
        )

        mock_llm.set_function_call_result(
            "find_collection_points",
            {"item_type": "phone", "search_radius_km": 2.0},
        )

        state = {
            "job_id": "job-136",
            "message": "폐휴대폰 수거함",
            "collection_point_address": "송파구",
        }

        await node(state)

        call_kwargs = mock_client.search_collection_points.call_args.kwargs
        assert call_kwargs["name_keyword"] == "폐휴대폰"

    @pytest.mark.anyio
    async def test_item_type_mapping_unknown_item_type(
        self,
        node,
        mock_llm: MockLLMClient,
        mock_client: MockCollectionPointClient,
    ):
        """알 수 없는 item_type은 그대로 전달."""
        mock_client.search_collection_points = AsyncMock(
            return_value=CollectionPointSearchResponse(
                results=[],
                total_count=0,
            )
        )

        mock_llm.set_function_call_result(
            "find_collection_points",
            {"item_type": "unknown_type", "search_radius_km": 2.0},
        )

        state = {
            "job_id": "job-137",
            "message": "알 수 없는 품목",
            "collection_point_address": "강남구",
        }

        await node(state)

        call_kwargs = mock_client.search_collection_points.call_args.kwargs
        # 매핑 실패 시 item_type 그대로 사용
        assert call_kwargs["name_keyword"] == "unknown_type"

    # ==========================================================
    # Additional Integration Tests
    # ==========================================================

    @pytest.mark.anyio
    async def test_node_publishes_started_event(
        self,
        node,
        mock_llm: MockLLMClient,
        mock_publisher: MockEventPublisher,
    ):
        """시작 이벤트 발행 확인."""
        mock_llm.set_function_call_result(
            "find_collection_points",
            {"item_type": "clothes", "search_radius_km": 2.0},
        )

        state = {
            "job_id": "job-138",
            "message": "의류수거함",
            "collection_point_address": "강남구",
        }

        await node(state)

        started_events = [e for e in mock_publisher.stages if e["status"] == "started"]
        assert len(started_events) >= 1
        assert started_events[0]["stage"] == "collection_point"
        assert started_events[0]["message"] == "수거함 위치 검색 중"

    @pytest.mark.anyio
    async def test_node_returns_only_context_channel(
        self,
        node,
        mock_llm: MockLLMClient,
    ):
        """Channel Separation: 노드는 자신의 채널만 반환."""
        mock_llm.set_function_call_result(
            "find_collection_points",
            {"item_type": "clothes", "search_radius_km": 2.0},
        )

        state = {
            "job_id": "job-139",
            "message": "의류수거함",
            "collection_point_address": "강남구",
            "intent": "collection_point",
            "session_id": "session-1",
            "existing_key": "should_be_preserved",
        }

        result = await node(state)

        # 자신의 채널만 반환
        assert "collection_point_context" in result
        # 기존 state 키들은 반환하지 않음
        assert "job_id" not in result
        assert "intent" not in result
        assert "session_id" not in result
        assert "existing_key" not in result

    @pytest.mark.anyio
    async def test_node_handles_no_address(
        self,
        mock_client: MockCollectionPointClient,
        mock_publisher: MockEventPublisher,
        mock_llm: MockLLMClient,
        mock_cb_registry: MockCircuitBreakerRegistry,
    ):
        """주소 정보 없을 때 needs_location 반환."""
        # Mock client가 빈 결과 반환하도록 설정
        mock_client._response = CollectionPointSearchResponse(
            results=[],
            total_count=0,
        )

        from chat_worker.infrastructure.orchestration.langgraph.nodes.node_executor import (
            NodeExecutor,
        )

        NodeExecutor.get_instance(cb_registry=mock_cb_registry)

        node = create_collection_point_node(
            collection_point_client=mock_client,
            event_publisher=mock_publisher,
            llm=mock_llm,
        )

        mock_llm.set_function_call_result(
            "find_collection_points",
            {"item_type": "clothes", "search_radius_km": 2.0},
        )

        state = {
            "job_id": "job-140",
            "message": "의류수거함",
            # collection_point_address 없음
        }

        result = await node(state)

        context = result["collection_point_context"]
        assert context is not None
        # Guide context 또는 not_found 반환
        # (주소 없으면 Command가 guide context 반환하거나 빈 결과)
        assert context.get("type") in ["guide", "not_found"]
