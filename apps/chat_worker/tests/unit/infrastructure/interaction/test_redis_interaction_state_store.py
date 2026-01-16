"""RedisInteractionStateStore 단위 테스트."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from chat_worker.domain import HumanInputRequest, InputType
from chat_worker.infrastructure.interaction.redis_interaction_state_store import (
    PENDING_REQUEST_PREFIX,
    PIPELINE_STATE_PREFIX,
    STATE_TTL,
    RedisInteractionStateStore,
)


class TestRedisInteractionStateStore:
    """RedisInteractionStateStore 테스트."""

    @pytest.fixture
    def mock_redis(self) -> AsyncMock:
        """Mock Redis."""
        redis = AsyncMock()
        redis.set = AsyncMock()
        redis.get = AsyncMock(return_value=None)
        redis.delete = AsyncMock()
        return redis

    @pytest.fixture
    def store(self, mock_redis: AsyncMock) -> RedisInteractionStateStore:
        """테스트용 Store."""
        return RedisInteractionStateStore(redis=mock_redis)

    @pytest.fixture
    def sample_request(self) -> HumanInputRequest:
        """샘플 요청."""
        return HumanInputRequest(
            job_id="job-123",
            input_type=InputType.LOCATION,
            message="위치 정보를 입력해주세요.",
            timeout=60,
        )

    # ==========================================================
    # save_pending_request Tests
    # ==========================================================

    @pytest.mark.asyncio
    async def test_save_pending_request(
        self,
        store: RedisInteractionStateStore,
        mock_redis: AsyncMock,
        sample_request: HumanInputRequest,
    ):
        """요청 저장."""
        await store.save_pending_request("job-123", sample_request)

        mock_redis.set.assert_called_once()
        call_args = mock_redis.set.call_args

        # 키 확인
        key = call_args[0][0]
        assert key == f"{PENDING_REQUEST_PREFIX}:job-123"

        # TTL 확인
        assert call_args.kwargs.get("ex") == STATE_TTL

    @pytest.mark.asyncio
    async def test_save_pending_request_serialization(
        self,
        store: RedisInteractionStateStore,
        mock_redis: AsyncMock,
        sample_request: HumanInputRequest,
    ):
        """직렬화 확인."""
        await store.save_pending_request("job-123", sample_request)

        call_args = mock_redis.set.call_args
        value = call_args[0][1]

        # JSON 파싱 가능해야 함
        data = json.loads(value)
        assert data["job_id"] == "job-123"
        assert data["input_type"] == "location"
        assert data["message"] == "위치 정보를 입력해주세요."

    # ==========================================================
    # get_pending_request Tests
    # ==========================================================

    @pytest.mark.asyncio
    async def test_get_pending_request_found(
        self,
        store: RedisInteractionStateStore,
        mock_redis: AsyncMock,
        sample_request: HumanInputRequest,
    ):
        """요청 조회 성공."""
        # Redis에서 반환될 값
        stored_data = json.dumps(
            {
                "job_id": "job-123",
                "input_type": "location",
                "message": "위치 정보를 입력해주세요.",
                "timeout": 60,
            }
        )
        mock_redis.get = AsyncMock(return_value=stored_data)

        result = await store.get_pending_request("job-123")

        assert result is not None
        assert result.job_id == "job-123"
        assert result.input_type == InputType.LOCATION

    @pytest.mark.asyncio
    async def test_get_pending_request_not_found(
        self,
        store: RedisInteractionStateStore,
        mock_redis: AsyncMock,
    ):
        """요청 조회 실패."""
        mock_redis.get = AsyncMock(return_value=None)

        result = await store.get_pending_request("non-existent")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_pending_request_key_format(
        self,
        store: RedisInteractionStateStore,
        mock_redis: AsyncMock,
    ):
        """키 형식 확인."""
        await store.get_pending_request("my-job-id")

        mock_redis.get.assert_called_once_with(f"{PENDING_REQUEST_PREFIX}:my-job-id")

    # ==========================================================
    # mark_completed Tests
    # ==========================================================

    @pytest.mark.asyncio
    async def test_mark_completed(
        self,
        store: RedisInteractionStateStore,
        mock_redis: AsyncMock,
    ):
        """완료 처리."""
        await store.mark_completed("job-456")

        mock_redis.delete.assert_called_once()

    # ==========================================================
    # save_pipeline_state Tests
    # ==========================================================

    @pytest.mark.asyncio
    async def test_save_pipeline_state(
        self,
        store: RedisInteractionStateStore,
        mock_redis: AsyncMock,
    ):
        """파이프라인 상태 저장."""
        state = {"message": "테스트", "intent": "waste"}

        await store.save_pipeline_state(
            job_id="job-abc",
            state=state,
            resume_node="rag_node",
        )

        mock_redis.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_save_pipeline_state_format(
        self,
        store: RedisInteractionStateStore,
        mock_redis: AsyncMock,
    ):
        """파이프라인 상태 저장 형식."""
        state = {"key": "value"}

        await store.save_pipeline_state(
            job_id="job-xyz",
            state=state,
            resume_node="answer_node",
        )

        call_args = mock_redis.set.call_args
        key = call_args[0][0]
        value = json.loads(call_args[0][1])

        assert key == f"{PIPELINE_STATE_PREFIX}:job-xyz"
        assert "state" in value
        assert "resume_node" in value
        assert value["state"] == state
        assert value["resume_node"] == "answer_node"

    # ==========================================================
    # get_pipeline_state Tests
    # ==========================================================

    @pytest.mark.asyncio
    async def test_get_pipeline_state_found(
        self,
        store: RedisInteractionStateStore,
        mock_redis: AsyncMock,
    ):
        """파이프라인 상태 조회 성공."""
        stored_data = json.dumps(
            {
                "state": {"message": "테스트"},
                "resume_node": "answer_node",
            }
        )
        mock_redis.get = AsyncMock(return_value=stored_data)

        result = await store.get_pipeline_state("job-123")

        assert result is not None
        state, resume_node = result
        assert state == {"message": "테스트"}
        assert resume_node == "answer_node"

    @pytest.mark.asyncio
    async def test_get_pipeline_state_not_found(
        self,
        store: RedisInteractionStateStore,
        mock_redis: AsyncMock,
    ):
        """파이프라인 상태 조회 실패."""
        mock_redis.get = AsyncMock(return_value=None)

        result = await store.get_pipeline_state("non-existent")

        assert result is None

    # ==========================================================
    # clear_state Tests
    # ==========================================================

    @pytest.mark.asyncio
    async def test_clear_state(
        self,
        store: RedisInteractionStateStore,
        mock_redis: AsyncMock,
    ):
        """전체 상태 삭제."""
        await store.clear_state("job-999")

        # delete가 호출되어야 함
        mock_redis.delete.assert_called_once()
        call_args = mock_redis.delete.call_args[0]
        # pending과 state 키 모두 삭제
        assert len(call_args) == 2
