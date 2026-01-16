"""HumanInteractionService 단위 테스트."""

from __future__ import annotations

from typing import Any

import pytest

from chat_worker.application.ports.input_requester import InputRequesterPort
from chat_worker.application.ports.interaction_state_store import InteractionStateStorePort
from chat_worker.application.services.human_interaction_service import (
    DEFAULT_MESSAGES,
    DEFAULT_TIMEOUT,
    HumanInteractionService,
)
from chat_worker.domain import HumanInputRequest, InputType


class MockInputRequester(InputRequesterPort):
    """테스트용 InputRequester Mock."""

    def __init__(self):
        self.request_input_called = False
        self.last_job_id: str | None = None
        self.last_input_type: InputType | None = None
        self.last_message: str | None = None
        self.last_timeout: int | None = None
        self._request_id = "req-123"

    async def request_input(
        self,
        job_id: str,
        input_type: InputType,
        message: str,
        timeout: int = 60,
    ) -> str:
        self.request_input_called = True
        self.last_job_id = job_id
        self.last_input_type = input_type
        self.last_message = message
        self.last_timeout = timeout
        return self._request_id


class MockStateStore(InteractionStateStorePort):
    """테스트용 StateStore Mock."""

    def __init__(self):
        self._pending_requests: dict[str, HumanInputRequest] = {}
        self._pipeline_states: dict[str, tuple[dict, str]] = {}
        self.save_pending_called = False
        self.save_pipeline_called = False
        self.mark_completed_called = False

    async def save_pending_request(
        self,
        job_id: str,
        request: HumanInputRequest,
    ) -> None:
        self.save_pending_called = True
        self._pending_requests[job_id] = request

    async def get_pending_request(
        self,
        job_id: str,
    ) -> HumanInputRequest | None:
        return self._pending_requests.get(job_id)

    async def mark_completed(self, job_id: str) -> None:
        self.mark_completed_called = True
        self._pending_requests.pop(job_id, None)
        self._pipeline_states.pop(job_id, None)

    async def save_pipeline_state(
        self,
        job_id: str,
        state: dict[str, Any],
        resume_node: str,
    ) -> None:
        self.save_pipeline_called = True
        self._pipeline_states[job_id] = (state, resume_node)

    async def get_pipeline_state(
        self,
        job_id: str,
    ) -> tuple[dict[str, Any], str] | None:
        return self._pipeline_states.get(job_id)

    async def clear_state(self, job_id: str) -> None:
        self._pending_requests.pop(job_id, None)
        self._pipeline_states.pop(job_id, None)


class TestHumanInteractionService:
    """HumanInteractionService 테스트 스위트."""

    @pytest.fixture
    def mock_requester(self) -> MockInputRequester:
        """Mock InputRequester."""
        return MockInputRequester()

    @pytest.fixture
    def mock_state_store(self) -> MockStateStore:
        """Mock StateStore."""
        return MockStateStore()

    @pytest.fixture
    def service(
        self,
        mock_requester: MockInputRequester,
        mock_state_store: MockStateStore,
    ) -> HumanInteractionService:
        """테스트용 서비스."""
        return HumanInteractionService(
            input_requester=mock_requester,
            state_store=mock_state_store,
        )

    # ==========================================================
    # request_location Tests
    # ==========================================================

    @pytest.mark.asyncio
    async def test_request_location_basic(
        self,
        service: HumanInteractionService,
        mock_requester: MockInputRequester,
        mock_state_store: MockStateStore,
    ):
        """기본 위치 요청."""
        job_id = "job-123"
        current_state = {"message": "테스트"}

        request_id = await service.request_location(
            job_id=job_id,
            current_state=current_state,
        )

        # 요청 ID 반환
        assert request_id == "req-123"

        # InputRequester 호출 확인
        assert mock_requester.request_input_called
        assert mock_requester.last_job_id == job_id
        assert mock_requester.last_input_type == InputType.LOCATION
        assert mock_requester.last_timeout == DEFAULT_TIMEOUT

        # StateStore 호출 확인
        assert mock_state_store.save_pipeline_called
        assert mock_state_store.save_pending_called

    @pytest.mark.asyncio
    async def test_request_location_with_custom_message(
        self,
        service: HumanInteractionService,
        mock_requester: MockInputRequester,
    ):
        """커스텀 메시지로 위치 요청."""
        custom_message = "위치 정보를 입력해주세요!"

        await service.request_location(
            job_id="job-1",
            current_state={},
            message=custom_message,
        )

        assert mock_requester.last_message == custom_message

    @pytest.mark.asyncio
    async def test_request_location_default_message(
        self,
        service: HumanInteractionService,
        mock_requester: MockInputRequester,
    ):
        """기본 메시지 사용."""
        await service.request_location(
            job_id="job-1",
            current_state={},
        )

        assert mock_requester.last_message == DEFAULT_MESSAGES[InputType.LOCATION]

    @pytest.mark.asyncio
    async def test_request_location_with_custom_timeout(
        self,
        service: HumanInteractionService,
        mock_requester: MockInputRequester,
    ):
        """커스텀 타임아웃."""
        await service.request_location(
            job_id="job-1",
            current_state={},
            timeout=120,
        )

        assert mock_requester.last_timeout == 120

    @pytest.mark.asyncio
    async def test_request_location_saves_pipeline_state(
        self,
        service: HumanInteractionService,
        mock_state_store: MockStateStore,
    ):
        """파이프라인 상태 저장 확인."""
        job_id = "job-123"
        current_state = {"key": "value", "nested": {"a": 1}}

        await service.request_location(
            job_id=job_id,
            current_state=current_state,
        )

        # 상태 조회로 확인
        result = await mock_state_store.get_pipeline_state(job_id)
        assert result is not None
        state, resume_node = result
        assert state == current_state
        assert resume_node == "location_subagent"

    @pytest.mark.asyncio
    async def test_request_location_saves_pending_request(
        self,
        service: HumanInteractionService,
        mock_state_store: MockStateStore,
    ):
        """대기 요청 저장 확인."""
        job_id = "job-123"

        await service.request_location(
            job_id=job_id,
            current_state={},
        )

        # 대기 요청 조회로 확인
        request = await mock_state_store.get_pending_request(job_id)
        assert request is not None
        assert request.job_id == job_id
        assert request.input_type == InputType.LOCATION

    # ==========================================================
    # request_confirmation Tests
    # ==========================================================

    @pytest.mark.asyncio
    async def test_request_confirmation(
        self,
        service: HumanInteractionService,
        mock_requester: MockInputRequester,
        mock_state_store: MockStateStore,
    ):
        """확인 요청."""
        job_id = "job-456"
        message = "정말 삭제할까요?"
        resume_node = "delete_node"

        request_id = await service.request_confirmation(
            job_id=job_id,
            current_state={"data": "test"},
            message=message,
            resume_node=resume_node,
        )

        assert request_id == "req-123"
        assert mock_requester.last_input_type == InputType.CONFIRMATION
        assert mock_requester.last_message == message

        # 파이프라인 상태 확인
        result = await mock_state_store.get_pipeline_state(job_id)
        assert result is not None
        _, saved_resume_node = result
        assert saved_resume_node == resume_node

    # ==========================================================
    # complete_interaction Tests
    # ==========================================================

    @pytest.mark.asyncio
    async def test_complete_interaction(
        self,
        service: HumanInteractionService,
        mock_state_store: MockStateStore,
    ):
        """상호작용 완료 처리."""
        job_id = "job-789"

        # 먼저 요청 생성
        await service.request_location(job_id=job_id, current_state={})

        # 완료 처리
        await service.complete_interaction(job_id)

        assert mock_state_store.mark_completed_called

    # ==========================================================
    # get_pending_state Tests
    # ==========================================================

    @pytest.mark.asyncio
    async def test_get_pending_state_exists(
        self,
        service: HumanInteractionService,
        mock_state_store: MockStateStore,
    ):
        """대기 상태 조회 (존재)."""
        job_id = "job-abc"
        state = {"key": "value"}

        await service.request_location(job_id=job_id, current_state=state)

        result = await service.get_pending_state(job_id)

        assert result is not None
        saved_state, resume_node = result
        assert saved_state == state
        assert resume_node == "location_subagent"

    @pytest.mark.asyncio
    async def test_get_pending_state_not_exists(
        self,
        service: HumanInteractionService,
    ):
        """대기 상태 조회 (없음)."""
        result = await service.get_pending_state("non-existent-job")

        assert result is None
