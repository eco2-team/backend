"""GetJobStatusQuery Unit Tests."""

import json
from unittest.mock import AsyncMock

import pytest

from chat.application.chat.queries.get_job_status import (
    GetJobStatusQuery,
    JobStatusResponse,
)


class TestJobStatusResponse:
    """JobStatusResponse DTO 테스트."""

    def test_response_all_fields(self) -> None:
        """모든 필드로 생성."""
        response = JobStatusResponse(
            job_id="job-123",
            status="running",
            progress=50,
            current_stage="rag",
            result={"answer": "test"},
            error=None,
        )

        assert response.job_id == "job-123"
        assert response.status == "running"
        assert response.progress == 50
        assert response.current_stage == "rag"
        assert response.result == {"answer": "test"}
        assert response.error is None

    def test_response_with_error(self) -> None:
        """에러가 있는 응답."""
        response = JobStatusResponse(
            job_id="job-123",
            status="failed",
            progress=0,
            current_stage="error",
            result=None,
            error="Something went wrong",
        )

        assert response.status == "failed"
        assert response.error == "Something went wrong"


class TestGetJobStatusQuery:
    """GetJobStatusQuery 유스케이스 테스트."""

    @pytest.fixture
    def mock_redis(self) -> AsyncMock:
        """Redis client Mock."""
        return AsyncMock()

    @pytest.fixture
    def query(self, mock_redis: AsyncMock) -> GetJobStatusQuery:
        """Query 인스턴스."""
        return GetJobStatusQuery(redis_client=mock_redis)

    @pytest.mark.asyncio
    async def test_execute_no_state_found(
        self,
        query: GetJobStatusQuery,
        mock_redis: AsyncMock,
    ) -> None:
        """상태 없을 때 unknown 반환."""
        mock_redis.get = AsyncMock(return_value=None)

        response = await query.execute("job-123")

        assert response.job_id == "job-123"
        assert response.status == "unknown"
        assert response.progress == 0
        assert response.current_stage is None
        assert response.result is None

    @pytest.mark.asyncio
    async def test_execute_queued_status(
        self,
        query: GetJobStatusQuery,
        mock_redis: AsyncMock,
    ) -> None:
        """queued 상태 매핑."""
        state_data = json.dumps({
            "stage": "queued",
            "status": "pending",
            "progress": 0,
        })
        mock_redis.get = AsyncMock(return_value=state_data)

        response = await query.execute("job-123")

        assert response.status == "queued"
        assert response.current_stage == "queued"
        assert response.progress == 0

    @pytest.mark.asyncio
    async def test_execute_running_status(
        self,
        query: GetJobStatusQuery,
        mock_redis: AsyncMock,
    ) -> None:
        """running 상태 매핑 (rag stage)."""
        state_data = json.dumps({
            "stage": "rag",
            "status": "processing",
            "progress": 30,
        })
        mock_redis.get = AsyncMock(return_value=state_data)

        response = await query.execute("job-123")

        assert response.status == "running"
        assert response.current_stage == "rag"
        assert response.progress == 30

    @pytest.mark.asyncio
    async def test_execute_completed_status(
        self,
        query: GetJobStatusQuery,
        mock_redis: AsyncMock,
    ) -> None:
        """completed 상태 매핑."""
        state_data = json.dumps({
            "stage": "done",
            "status": "completed",
            "progress": 100,
            "result": {"answer": "This is the answer"},
        })
        mock_redis.get = AsyncMock(return_value=state_data)

        response = await query.execute("job-123")

        assert response.status == "completed"
        assert response.current_stage == "done"
        assert response.progress == 100
        assert response.result == {"answer": "This is the answer"}

    @pytest.mark.asyncio
    async def test_execute_failed_status(
        self,
        query: GetJobStatusQuery,
        mock_redis: AsyncMock,
    ) -> None:
        """failed 상태 매핑."""
        state_data = json.dumps({
            "stage": "done",
            "status": "failed",
            "progress": 50,
            "error": "LLM API error",
        })
        mock_redis.get = AsyncMock(return_value=state_data)

        response = await query.execute("job-123")

        assert response.status == "failed"
        assert response.current_stage == "done"
        assert response.error == "LLM API error"

    @pytest.mark.asyncio
    async def test_execute_bytes_response(
        self,
        query: GetJobStatusQuery,
        mock_redis: AsyncMock,
    ) -> None:
        """bytes로 반환된 데이터 처리."""
        state_data = json.dumps({
            "stage": "intent",
            "status": "processing",
            "progress": 10,
        }).encode("utf-8")
        mock_redis.get = AsyncMock(return_value=state_data)

        response = await query.execute("job-123")

        assert response.status == "running"
        assert response.current_stage == "intent"
        assert response.progress == 10

    @pytest.mark.asyncio
    async def test_execute_invalid_json(
        self,
        query: GetJobStatusQuery,
        mock_redis: AsyncMock,
    ) -> None:
        """잘못된 JSON 데이터 처리."""
        mock_redis.get = AsyncMock(return_value="invalid json {")

        response = await query.execute("job-123")

        assert response.status == "error"
        assert "Invalid state data" in response.error

    @pytest.mark.asyncio
    async def test_execute_redis_error(
        self,
        query: GetJobStatusQuery,
        mock_redis: AsyncMock,
    ) -> None:
        """Redis 에러 처리."""
        mock_redis.get = AsyncMock(side_effect=Exception("Connection refused"))

        response = await query.execute("job-123")

        assert response.status == "error"
        assert "Connection refused" in response.error

    @pytest.mark.asyncio
    async def test_execute_progress_parsing_string(
        self,
        query: GetJobStatusQuery,
        mock_redis: AsyncMock,
    ) -> None:
        """progress가 문자열인 경우."""
        state_data = json.dumps({
            "stage": "rag",
            "status": "processing",
            "progress": "45",
        })
        mock_redis.get = AsyncMock(return_value=state_data)

        response = await query.execute("job-123")

        assert response.progress == 45

    @pytest.mark.asyncio
    async def test_execute_progress_parsing_invalid(
        self,
        query: GetJobStatusQuery,
        mock_redis: AsyncMock,
    ) -> None:
        """progress가 유효하지 않은 경우."""
        state_data = json.dumps({
            "stage": "rag",
            "status": "processing",
            "progress": "invalid",
        })
        mock_redis.get = AsyncMock(return_value=state_data)

        response = await query.execute("job-123")

        assert response.progress == 0

    @pytest.mark.asyncio
    async def test_execute_progress_parsing_none(
        self,
        query: GetJobStatusQuery,
        mock_redis: AsyncMock,
    ) -> None:
        """progress가 None인 경우."""
        state_data = json.dumps({
            "stage": "rag",
            "status": "processing",
            "progress": None,
        })
        mock_redis.get = AsyncMock(return_value=state_data)

        response = await query.execute("job-123")

        assert response.progress == 0

    @pytest.mark.asyncio
    async def test_execute_missing_fields(
        self,
        query: GetJobStatusQuery,
        mock_redis: AsyncMock,
    ) -> None:
        """필수 필드 없을 때 기본값 사용."""
        state_data = json.dumps({})
        mock_redis.get = AsyncMock(return_value=state_data)

        response = await query.execute("job-123")

        # stage가 없으면 "unknown"이 되고, running으로 매핑
        assert response.status == "running"
        assert response.current_stage == "unknown"
        assert response.progress == 0

    @pytest.mark.asyncio
    async def test_execute_various_stages_mapped_to_running(
        self,
        query: GetJobStatusQuery,
        mock_redis: AsyncMock,
    ) -> None:
        """다양한 stage가 running으로 매핑."""
        stages = ["intent", "vision", "rag", "answer", "subagent"]

        for stage in stages:
            state_data = json.dumps({
                "stage": stage,
                "status": "processing",
                "progress": 50,
            })
            mock_redis.get = AsyncMock(return_value=state_data)

            response = await query.execute("job-123")

            assert response.status == "running", f"Stage {stage} should map to running"
            assert response.current_stage == stage

    @pytest.mark.asyncio
    async def test_execute_state_key_format(
        self,
        query: GetJobStatusQuery,
        mock_redis: AsyncMock,
    ) -> None:
        """올바른 state key 형식 사용."""
        mock_redis.get = AsyncMock(return_value=None)

        await query.execute("my-job-id")

        mock_redis.get.assert_called_once_with("chat:state:my-job-id")
