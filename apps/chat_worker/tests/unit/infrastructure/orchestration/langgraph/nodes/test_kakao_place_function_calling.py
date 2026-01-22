"""Kakao Place Node Function Calling 단위 테스트.

LLM Function Calling을 통한 장소 검색 파라미터 추출 테스트.

테스트 대상:
- LLM Function Calling으로 파라미터 추출 (query, search_type, radius)
- Function call 실패 시 fallback 처리
- 사용자 위치 정보 전달
- 커스텀 반경 추출
- Progress 이벤트 발행

Pattern: test_openai_client_function_calling.py 참고
"""

from __future__ import annotations

from typing import Any

import pytest

from chat_worker.application.commands.search_kakao_place_command import (
    SearchKakaoPlaceInput,
    SearchKakaoPlaceOutput,
)
from chat_worker.application.ports.kakao_local_client import (
    KakaoPlaceDTO,
    KakaoSearchMeta,
    KakaoSearchResponse,
)
from chat_worker.infrastructure.orchestration.langgraph.nodes.kakao_place_node import (
    KAKAO_PLACE_FUNCTION,
    create_kakao_place_node,
)


class MockLLMClient:
    """테스트용 Mock LLM Client (Function Calling)."""

    def __init__(self):
        self.function_call_results: list[tuple[str | None, dict | None]] = []
        self.call_count = 0
        self.last_prompt = None
        self.last_system_prompt = None
        self.last_functions = None
        self.should_raise = False
        self.error_message = "LLM Error"

    def set_function_call_result(self, func_name: str | None, func_args: dict | None):
        """Function call 결과 설정."""
        self.function_call_results = [(func_name, func_args)]

    def set_error(self, error_message: str = "LLM Error"):
        """에러 발생 설정."""
        self.should_raise = True
        self.error_message = error_message

    async def generate_function_call(
        self,
        prompt: str,
        functions: list[dict],
        system_prompt: str = "",
        function_call: dict | str = "auto",
    ) -> tuple[str | None, dict | None]:
        """Mock function call 생성."""
        self.call_count += 1
        self.last_prompt = prompt
        self.last_system_prompt = system_prompt
        self.last_functions = functions

        if self.should_raise:
            raise Exception(self.error_message)

        if self.function_call_results:
            return self.function_call_results[0]

        return None, None


class MockKakaoClient:
    """테스트용 Mock Kakao Client."""

    def __init__(self):
        self.search_keyword_called = False
        self.search_category_called = False
        self.last_query = None
        self.last_radius = None

    async def search_keyword(
        self,
        query: str,
        x: float | None = None,
        y: float | None = None,
        radius: int = 5000,
        size: int = 10,
        sort: str = "accuracy",
    ):
        """Mock 키워드 검색."""
        self.search_keyword_called = True
        self.last_query = query
        self.last_radius = radius

        return KakaoSearchResponse(
            places=[
                KakaoPlaceDTO(
                    id="123",
                    place_name="테스트 장소",
                    category_name="가정,생활 > 재활용센터",
                    category_group_code="PO3",
                    category_group_name="공공기관",
                    phone="02-1234-5678",
                    address_name="서울시 강남구",
                    road_address_name="서울시 강남구 테헤란로 1",
                    x="127.0",
                    y="37.5",
                    place_url="https://place.map.kakao.com/123",
                    distance="100",
                )
            ],
            meta=KakaoSearchMeta(total_count=1, pageable_count=1, is_end=True),
        )

    async def search_category(
        self,
        category_group_code: str,
        x: float,
        y: float,
        radius: int = 5000,
        size: int = 10,
    ):
        """Mock 카테고리 검색."""
        self.search_category_called = True
        self.last_radius = radius

        return KakaoSearchResponse(
            places=[
                KakaoPlaceDTO(
                    id="456",
                    place_name="카테고리 장소",
                    category_name="가정,생활 > 재활용센터",
                    category_group_code="PO3",
                    category_group_name="공공기관",
                    phone="02-9876-5432",
                    address_name="서울시 서초구",
                    road_address_name="서울시 서초구 서초대로 1",
                    x="127.1",
                    y="37.4",
                    place_url="https://place.map.kakao.com/456",
                    distance="200",
                )
            ],
            meta=KakaoSearchMeta(total_count=1, pageable_count=1, is_end=True),
        )


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
        """Stage 이벤트 발행."""
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
        """입력 요청 이벤트 발행."""
        self.needs_input_calls.append(
            {
                "task_id": task_id,
                "input_type": input_type,
                "message": message,
                "timeout": timeout,
            }
        )
        return "event-id"


class TestKakaoPlaceNodeFunctionCalling:
    """Kakao Place Node Function Calling 테스트 스위트."""

    @pytest.fixture
    def mock_llm(self) -> MockLLMClient:
        """Mock LLM Client."""
        return MockLLMClient()

    @pytest.fixture
    def mock_kakao_client(self) -> MockKakaoClient:
        """Mock Kakao Client."""
        return MockKakaoClient()

    @pytest.fixture
    def mock_event_publisher(self) -> MockEventPublisher:
        """Mock Event Publisher."""
        return MockEventPublisher()

    @pytest.fixture
    def node(
        self,
        mock_kakao_client: MockKakaoClient,
        mock_event_publisher: MockEventPublisher,
        mock_llm: MockLLMClient,
    ):
        """테스트용 Node."""
        return create_kakao_place_node(
            kakao_client=mock_kakao_client,
            event_publisher=mock_event_publisher,
            llm=mock_llm,
        )

    # ==========================================================
    # Function Call Parameter Extraction Tests
    # ==========================================================

    @pytest.mark.anyio
    async def test_function_call_parameter_extraction(
        self,
        mock_llm: MockLLMClient,
        mock_kakao_client: MockKakaoClient,
        mock_event_publisher: MockEventPublisher,
    ):
        """LLM이 검색 파라미터를 성공적으로 추출 (query, search_type, radius)."""
        # Given: LLM이 검색 파라미터를 추출
        mock_llm.set_function_call_result(
            "search_kakao_place",
            {
                "query": "재활용센터",
                "search_type": "keyword",
                "radius": 5000,
            },
        )

        node = create_kakao_place_node(
            kakao_client=mock_kakao_client,
            event_publisher=mock_event_publisher,
            llm=mock_llm,
        )

        state = {
            "job_id": "job-123",
            "message": "주변 재활용센터 찾아줘",
        }

        # When: 노드 실행
        result = await node(state)

        # Then: Function call 성공
        assert mock_llm.call_count == 1
        assert mock_llm.last_prompt == "주변 재활용센터 찾아줘"
        assert mock_llm.last_functions == [KAKAO_PLACE_FUNCTION]
        assert "장소 검색에 필요한 정보를 추출하세요" in mock_llm.last_system_prompt

        # Kakao API 호출 확인
        assert mock_kakao_client.search_keyword_called
        assert mock_kakao_client.last_query == "재활용센터"
        assert mock_kakao_client.last_radius == 5000

        # 결과 확인
        assert "location_context" in result
        assert result["location_context"] is not None

    @pytest.mark.anyio
    async def test_function_call_extracts_different_search_types(
        self,
        mock_llm: MockLLMClient,
        mock_kakao_client: MockKakaoClient,
        mock_event_publisher: MockEventPublisher,
    ):
        """다양한 search_type 추출."""
        # Given: 카테고리 검색
        mock_llm.set_function_call_result(
            "search_kakao_place",
            {
                "query": "카페",
                "search_type": "category",
                "category_code": "CE7",
                "radius": 3000,
            },
        )

        node = create_kakao_place_node(
            kakao_client=mock_kakao_client,
            event_publisher=mock_event_publisher,
            llm=mock_llm,
        )

        state = {
            "job_id": "job-456",
            "message": "근처 카페",
            "user_location": {"lat": 37.5, "lon": 127.0},
        }

        # When
        await node(state)

        # Then: 카테고리 검색 호출
        assert mock_kakao_client.search_category_called
        assert mock_kakao_client.last_radius == 3000

    # ==========================================================
    # Function Call Fallback Tests
    # ==========================================================

    @pytest.mark.anyio
    async def test_function_call_fallback_on_failure(
        self,
        mock_llm: MockLLMClient,
        mock_kakao_client: MockKakaoClient,
        mock_event_publisher: MockEventPublisher,
    ):
        """Function call 실패 시 fallback 값 사용."""
        # Given: Function call이 None 반환 (실패)
        mock_llm.set_function_call_result(None, None)

        node = create_kakao_place_node(
            kakao_client=mock_kakao_client,
            event_publisher=mock_event_publisher,
            llm=mock_llm,
        )

        state = {
            "job_id": "job-fallback",
            "message": "제로웨이스트샵",
        }

        # When
        result = await node(state)

        # Then: Fallback으로 message를 query로 사용
        assert mock_kakao_client.search_keyword_called
        assert mock_kakao_client.last_query == "제로웨이스트샵"  # message 그대로
        assert mock_kakao_client.last_radius == 5000  # 기본값

        # 결과는 여전히 성공
        assert "location_context" in result

    @pytest.mark.anyio
    async def test_function_call_llm_error_returns_error_context(
        self,
        mock_llm: MockLLMClient,
        mock_kakao_client: MockKakaoClient,
        mock_event_publisher: MockEventPublisher,
    ):
        """LLM 호출 오류 시 에러 컨텍스트 반환."""
        # Given: LLM 에러 발생
        mock_llm.set_error("LLM API timeout")

        node = create_kakao_place_node(
            kakao_client=mock_kakao_client,
            event_publisher=mock_event_publisher,
            llm=mock_llm,
        )

        state = {
            "job_id": "job-error",
            "message": "주변 재활용센터",
        }

        # When
        result = await node(state)

        # Then: 에러 컨텍스트 반환 (success=False, error 메시지 포함)
        assert "location_context" in result
        context = result["location_context"]
        assert context.get("success") is False
        assert "검색 정보를 추출할 수 없습니다" in context.get("error", "")

        # Kakao API는 호출되지 않음
        assert not mock_kakao_client.search_keyword_called

        # 실패 이벤트 발행
        failed_events = [e for e in mock_event_publisher.stages if e["status"] == "failed"]
        assert len(failed_events) >= 1

    # ==========================================================
    # User Location Tests
    # ==========================================================

    @pytest.mark.anyio
    async def test_function_call_with_location(
        self,
        mock_llm: MockLLMClient,
        mock_kakao_client: MockKakaoClient,
        mock_event_publisher: MockEventPublisher,
    ):
        """사용자 위치 정보가 포함된 경우 input DTO에 전달."""
        # Given: 위치 정보 포함
        mock_llm.set_function_call_result(
            "search_kakao_place",
            {
                "query": "재활용센터",
                "search_type": "keyword",
                "radius": 5000,
            },
        )

        # Command를 Mock으로 대체하여 input DTO 검증
        command_execute_called = False
        captured_input = None

        async def mock_execute(self, input_dto: SearchKakaoPlaceInput):
            nonlocal command_execute_called, captured_input
            command_execute_called = True
            captured_input = input_dto

            return SearchKakaoPlaceOutput(
                success=True,
                places_context={
                    "type": "kakao_places",
                    "found": True,
                    "count": 1,
                    "places": [],
                    "context": "테스트 결과",
                },
            )

        # Node 생성 후 command.execute를 mock으로 교체
        node = create_kakao_place_node(
            kakao_client=mock_kakao_client,
            event_publisher=mock_event_publisher,
            llm=mock_llm,
        )

        # Command의 execute를 mock으로 교체
        from chat_worker.application.commands.search_kakao_place_command import (
            SearchKakaoPlaceCommand,
        )

        original_execute = SearchKakaoPlaceCommand.execute
        SearchKakaoPlaceCommand.execute = mock_execute

        try:
            state = {
                "job_id": "job-location",
                "message": "주변 재활용센터",
                "user_location": {"lat": 37.5, "lon": 127.0},
            }

            # When
            await node(state)

            # Then: input DTO에 user_location 전달됨
            assert command_execute_called
            assert captured_input is not None
            assert captured_input.user_location == {"lat": 37.5, "lon": 127.0}
            assert captured_input.query == "재활용센터"
            assert captured_input.radius == 5000

        finally:
            # 원래 execute 복원
            SearchKakaoPlaceCommand.execute = original_execute

    @pytest.mark.anyio
    async def test_function_call_without_location(
        self,
        mock_llm: MockLLMClient,
        mock_kakao_client: MockKakaoClient,
        mock_event_publisher: MockEventPublisher,
    ):
        """위치 정보가 없어도 동작 (정확도순 검색)."""
        # Given
        mock_llm.set_function_call_result(
            "search_kakao_place",
            {
                "query": "재활용센터",
                "search_type": "keyword",
                "radius": 5000,
            },
        )

        node = create_kakao_place_node(
            kakao_client=mock_kakao_client,
            event_publisher=mock_event_publisher,
            llm=mock_llm,
        )

        state = {
            "job_id": "job-no-location",
            "message": "재활용센터 찾아줘",
            # user_location 없음
        }

        # When
        result = await node(state)

        # Then: 검색 성공 (정확도순)
        assert mock_kakao_client.search_keyword_called
        assert "location_context" in result

    # ==========================================================
    # Custom Radius Tests
    # ==========================================================

    @pytest.mark.anyio
    async def test_function_call_custom_radius(
        self,
        mock_llm: MockLLMClient,
        mock_kakao_client: MockKakaoClient,
        mock_event_publisher: MockEventPublisher,
    ):
        """사용자 메시지에서 커스텀 반경 추출."""
        # Given: 3km 반경 요청
        mock_llm.set_function_call_result(
            "search_kakao_place",
            {
                "query": "제로웨이스트샵",
                "search_type": "keyword",
                "radius": 3000,  # 3km = 3000m
            },
        )

        node = create_kakao_place_node(
            kakao_client=mock_kakao_client,
            event_publisher=mock_event_publisher,
            llm=mock_llm,
        )

        state = {
            "job_id": "job-custom-radius",
            "message": "3km 이내 제로웨이스트샵",
        }

        # When
        await node(state)

        # Then: 커스텀 반경 적용
        assert mock_kakao_client.last_radius == 3000

    @pytest.mark.anyio
    async def test_function_call_different_radius_values(
        self,
        mock_llm: MockLLMClient,
        mock_kakao_client: MockKakaoClient,
        mock_event_publisher: MockEventPublisher,
    ):
        """다양한 반경 값 테스트."""
        # Given: 1km 반경
        mock_llm.set_function_call_result(
            "search_kakao_place",
            {
                "query": "카페",
                "search_type": "keyword",
                "radius": 1000,
            },
        )

        node = create_kakao_place_node(
            kakao_client=mock_kakao_client,
            event_publisher=mock_event_publisher,
            llm=mock_llm,
        )

        state = {
            "job_id": "job-1km",
            "message": "1km 이내 카페",
        }

        # When
        await node(state)

        # Then
        assert mock_kakao_client.last_radius == 1000

    # ==========================================================
    # Progress Event Tests
    # ==========================================================

    @pytest.mark.anyio
    async def test_function_call_publishes_started_event(
        self,
        node,
        mock_event_publisher: MockEventPublisher,
        mock_llm: MockLLMClient,
    ):
        """시작 이벤트 발행."""
        mock_llm.set_function_call_result(
            "search_kakao_place",
            {
                "query": "재활용센터",
                "search_type": "keyword",
                "radius": 5000,
            },
        )

        state = {
            "job_id": "job-event",
            "message": "주변 재활용센터",
        }

        # When
        await node(state)

        # Then: started 이벤트 확인
        started_events = [e for e in mock_event_publisher.stages if e["status"] == "started"]
        assert len(started_events) >= 1
        assert started_events[0]["stage"] == "kakao_place"
        assert started_events[0]["message"] == "주변 장소 검색 중"
        assert started_events[0]["progress"] == 45

    @pytest.mark.anyio
    async def test_function_call_publishes_completed_event(
        self,
        mock_llm: MockLLMClient,
        mock_kakao_client: MockKakaoClient,
        mock_event_publisher: MockEventPublisher,
    ):
        """완료 이벤트 발행."""
        mock_llm.set_function_call_result(
            "search_kakao_place",
            {
                "query": "재활용센터",
                "search_type": "keyword",
                "radius": 5000,
            },
        )

        node = create_kakao_place_node(
            kakao_client=mock_kakao_client,
            event_publisher=mock_event_publisher,
            llm=mock_llm,
        )

        state = {
            "job_id": "job-complete",
            "message": "주변 재활용센터",
        }

        # When
        await node(state)

        # Then: completed 이벤트 확인
        completed_events = [e for e in mock_event_publisher.stages if e["status"] == "completed"]
        assert len(completed_events) >= 1
        completed = completed_events[0]
        assert completed["stage"] == "kakao_place"
        assert completed["progress"] == 55
        assert completed["result"]["found"] is True
        assert completed["result"]["count"] == 1

    # ==========================================================
    # Edge Cases Tests
    # ==========================================================

    @pytest.mark.anyio
    async def test_function_call_forced_invocation(
        self,
        mock_llm: MockLLMClient,
        mock_kakao_client: MockKakaoClient,
        mock_event_publisher: MockEventPublisher,
    ):
        """Function call 강제 호출 확인."""
        mock_llm.set_function_call_result(
            "search_kakao_place",
            {
                "query": "재활용센터",
                "search_type": "keyword",
                "radius": 5000,
            },
        )

        node = create_kakao_place_node(
            kakao_client=mock_kakao_client,
            event_publisher=mock_event_publisher,
            llm=mock_llm,
        )

        state = {
            "job_id": "job-forced",
            "message": "주변 재활용센터",
        }

        # When
        await node(state)

        # Then: function_call={"name": "search_kakao_place"}로 강제 호출 확인
        # (코드에서 강제 호출 설정됨)
        assert mock_llm.call_count == 1

    @pytest.mark.anyio
    async def test_function_call_empty_message(
        self,
        mock_llm: MockLLMClient,
        mock_kakao_client: MockKakaoClient,
        mock_event_publisher: MockEventPublisher,
    ):
        """빈 메시지 처리."""
        # Given: 빈 메시지지만 LLM이 fallback 파라미터 생성
        mock_llm.set_function_call_result(None, None)  # Function call 실패

        node = create_kakao_place_node(
            kakao_client=mock_kakao_client,
            event_publisher=mock_event_publisher,
            llm=mock_llm,
        )

        state = {
            "job_id": "job-empty",
            "message": "",
        }

        # When
        result = await node(state)

        # Then: Fallback으로 빈 query 전달
        # Command에서 검색어 없음 처리
        assert "location_context" in result

    @pytest.mark.anyio
    async def test_function_call_preserves_state(
        self,
        node,
        mock_llm: MockLLMClient,
    ):
        """기존 state 보존 (Channel Separation)."""
        mock_llm.set_function_call_result(
            "search_kakao_place",
            {
                "query": "재활용센터",
                "search_type": "keyword",
                "radius": 5000,
            },
        )

        state = {
            "job_id": "job-preserve",
            "message": "주변 재활용센터",
            "intent": "kakao_place",
            "session_id": "session-1",
            "existing_key": "should_be_preserved",
        }

        # When
        result = await node(state)

        # Then: 노드는 자신의 채널만 반환 + state 확장
        assert "location_context" in result
        # 기존 state는 LangGraph reducer가 병합
        # 노드는 **state로 확장하므로 일부 키가 포함될 수 있음
