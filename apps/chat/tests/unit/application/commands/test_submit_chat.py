"""SubmitChatCommand Unit Tests."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from chat.application.chat.commands.submit_chat import (
    SubmitChatCommand,
    SubmitChatRequest,
    SubmitChatResponse,
)


class TestSubmitChatRequest:
    """SubmitChatRequest DTO 테스트."""

    def test_request_required_fields(self) -> None:
        """필수 필드만으로 생성."""
        request = SubmitChatRequest(
            session_id="session-123",
            user_id="user-456",
            message="Hello",
        )

        assert request.session_id == "session-123"
        assert request.user_id == "user-456"
        assert request.message == "Hello"
        assert request.image_url is None
        assert request.user_location is None
        assert request.model is None

    def test_request_all_fields(self) -> None:
        """모든 필드로 생성."""
        location = {"lat": 37.5, "lng": 127.0}
        request = SubmitChatRequest(
            session_id="session-123",
            user_id="user-456",
            message="What is this?",
            image_url="https://example.com/image.jpg",
            user_location=location,
            model="gpt-5.2",
        )

        assert request.image_url == "https://example.com/image.jpg"
        assert request.user_location == location
        assert request.model == "gpt-5.2"


class TestSubmitChatResponse:
    """SubmitChatResponse DTO 테스트."""

    def test_response_creation(self) -> None:
        """응답 DTO 생성."""
        response = SubmitChatResponse(
            job_id="job-123",
            session_id="session-456",
            stream_url="/api/v1/chat/job-123/events",
            status="submitted",
        )

        assert response.job_id == "job-123"
        assert response.session_id == "session-456"
        assert response.stream_url == "/api/v1/chat/job-123/events"
        assert response.status == "submitted"


class TestSubmitChatCommand:
    """SubmitChatCommand 유스케이스 테스트."""

    @pytest.fixture
    def mock_job_submitter(self) -> AsyncMock:
        """JobSubmitter Mock."""
        submitter = AsyncMock()
        submitter.submit = AsyncMock(return_value=True)
        return submitter

    @pytest.fixture
    def command(self, mock_job_submitter: AsyncMock) -> SubmitChatCommand:
        """Command 인스턴스."""
        return SubmitChatCommand(job_submitter=mock_job_submitter)

    @pytest.mark.asyncio
    async def test_execute_success(
        self,
        command: SubmitChatCommand,
        mock_job_submitter: AsyncMock,
    ) -> None:
        """성공적인 작업 제출."""
        request = SubmitChatRequest(
            session_id="session-123",
            user_id="user-456",
            message="Hello",
        )

        response = await command.execute(request)

        assert response.session_id == "session-123"
        assert response.status == "submitted"
        assert response.job_id is not None
        assert "/api/v1/chat/" in response.stream_url
        assert "/events" in response.stream_url

        mock_job_submitter.submit.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_generates_unique_job_id(
        self,
        command: SubmitChatCommand,
    ) -> None:
        """각 실행마다 고유 job_id 생성."""
        request = SubmitChatRequest(
            session_id="session-123",
            user_id="user-456",
            message="Hello",
        )

        response1 = await command.execute(request)
        response2 = await command.execute(request)

        assert response1.job_id != response2.job_id

    @pytest.mark.asyncio
    async def test_execute_passes_all_parameters(
        self,
        command: SubmitChatCommand,
        mock_job_submitter: AsyncMock,
    ) -> None:
        """모든 파라미터가 JobSubmitter에 전달."""
        location = {"lat": 37.5, "lng": 127.0}
        request = SubmitChatRequest(
            session_id="session-123",
            user_id="user-456",
            message="What is this?",
            image_url="https://example.com/image.jpg",
            user_location=location,
            model="gpt-5.2",
        )

        await command.execute(request)

        call_kwargs = mock_job_submitter.submit.call_args.kwargs
        assert call_kwargs["session_id"] == "session-123"
        assert call_kwargs["user_id"] == "user-456"
        assert call_kwargs["message"] == "What is this?"
        assert call_kwargs["image_url"] == "https://example.com/image.jpg"
        assert call_kwargs["user_location"] == location
        assert call_kwargs["model"] == "gpt-5.2"

    @pytest.mark.asyncio
    async def test_execute_submission_failure_returns_response(
        self,
        mock_job_submitter: AsyncMock,
    ) -> None:
        """제출 실패 시에도 응답 반환."""
        mock_job_submitter.submit = AsyncMock(return_value=False)
        command = SubmitChatCommand(job_submitter=mock_job_submitter)

        request = SubmitChatRequest(
            session_id="session-123",
            user_id="user-456",
            message="Hello",
        )

        response = await command.execute(request)

        # 실패해도 job_id와 응답은 반환됨 (클라이언트 재시도 가능)
        assert response.job_id is not None
        assert response.status == "submitted"

    @pytest.mark.asyncio
    async def test_execute_stream_url_format(
        self,
        command: SubmitChatCommand,
    ) -> None:
        """stream_url 형식 검증."""
        request = SubmitChatRequest(
            session_id="session-123",
            user_id="user-456",
            message="Hello",
        )

        response = await command.execute(request)

        expected_url = f"/api/v1/chat/{response.job_id}/events"
        assert response.stream_url == expected_url

    @pytest.mark.asyncio
    async def test_execute_with_none_optional_fields(
        self,
        command: SubmitChatCommand,
        mock_job_submitter: AsyncMock,
    ) -> None:
        """선택적 필드 None 전달."""
        request = SubmitChatRequest(
            session_id="session-123",
            user_id="user-456",
            message="Hello",
            image_url=None,
            user_location=None,
            model=None,
        )

        await command.execute(request)

        call_kwargs = mock_job_submitter.submit.call_args.kwargs
        assert call_kwargs["image_url"] is None
        assert call_kwargs["user_location"] is None
        assert call_kwargs["model"] is None
