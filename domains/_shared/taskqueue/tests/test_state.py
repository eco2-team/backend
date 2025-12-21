"""Tests for TaskState management."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from domains._shared.taskqueue.state import (
    STEP_PROGRESS,
    TaskState,
    TaskStateManager,
    TaskStatus,
    TaskStep,
)


class TestTaskStatus:
    """TaskStatus enum tests."""

    def test_values(self):
        assert TaskStatus.QUEUED.value == "queued"
        assert TaskStatus.PROCESSING.value == "processing"
        assert TaskStatus.COMPLETED.value == "completed"
        assert TaskStatus.FAILED.value == "failed"


class TestTaskStep:
    """TaskStep enum tests."""

    def test_values(self):
        assert TaskStep.PENDING.value == "pending"
        assert TaskStep.SCAN.value == "scan"
        assert TaskStep.ANALYZE.value == "analyze"
        assert TaskStep.ANSWER.value == "answer"
        assert TaskStep.COMPLETE.value == "complete"

    def test_progress_mapping(self):
        assert STEP_PROGRESS[TaskStep.PENDING] == 0
        assert STEP_PROGRESS[TaskStep.SCAN] == 15
        assert STEP_PROGRESS[TaskStep.ANALYZE] == 50
        assert STEP_PROGRESS[TaskStep.ANSWER] == 75
        assert STEP_PROGRESS[TaskStep.COMPLETE] == 100


class TestTaskState:
    """TaskState dataclass tests."""

    def test_default_values(self):
        state = TaskState(task_id="test-123", user_id="user-456")

        assert state.task_id == "test-123"
        assert state.user_id == "user-456"
        assert state.status == TaskStatus.QUEUED
        assert state.step == TaskStep.PENDING
        assert state.progress == 0
        assert state.partial_result == {}
        assert state.result is None
        assert state.reward_status == "pending"

    def test_to_dict(self):
        state = TaskState(
            task_id="test-123",
            user_id="user-456",
            status=TaskStatus.PROCESSING,
            step=TaskStep.SCAN,
            progress=25,
            partial_result={"classification": {"major": "재활용"}},
        )

        data = state.to_dict()

        assert data["task_id"] == "test-123"
        assert data["status"] == "processing"
        assert data["step"] == "scan"
        assert data["progress"] == 25
        assert json.loads(data["partial_result"]) == {"classification": {"major": "재활용"}}

    def test_from_dict(self):
        data = {
            "task_id": "test-123",
            "user_id": "user-456",
            "status": "completed",
            "step": "complete",
            "progress": "100",
            "partial_result": json.dumps({"classification": {"major": "재활용"}}),
            "result": json.dumps({"final": "result"}),
            "metadata": json.dumps({"duration": 5.5}),
            "reward_status": "granted",
            "created_at": "2025-12-21T00:00:00Z",
            "updated_at": "2025-12-21T00:01:00Z",
        }

        state = TaskState.from_dict(data)

        assert state.task_id == "test-123"
        assert state.status == TaskStatus.COMPLETED
        assert state.step == TaskStep.COMPLETE
        assert state.progress == 100
        assert state.partial_result == {"classification": {"major": "재활용"}}
        assert state.result == {"final": "result"}
        assert state.metadata == {"duration": 5.5}


class TestTaskStateManager:
    """TaskStateManager tests."""

    @pytest.fixture
    def mock_redis(self):
        """Create mock Redis client."""
        redis = AsyncMock()
        redis.hset = AsyncMock()
        redis.hgetall = AsyncMock(return_value={})
        redis.hget = AsyncMock(return_value=None)
        redis.expire = AsyncMock()
        redis.delete = AsyncMock()
        redis.close = AsyncMock()
        return redis

    @pytest.fixture
    def manager(self, mock_redis):
        """Create manager with mock Redis."""
        manager = TaskStateManager()
        manager._redis = mock_redis
        return manager

    @pytest.mark.asyncio
    async def test_create(self, manager, mock_redis):
        state = TaskState(task_id="test-123", user_id="user-456")

        await manager.create(state)

        mock_redis.hset.assert_called_once()
        call_args = mock_redis.hset.call_args
        assert call_args[0][0] == "task:test-123"
        mock_redis.expire.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_status(self, manager, mock_redis):
        await manager.update("test-123", status=TaskStatus.PROCESSING)

        mock_redis.hset.assert_called_once()
        call_args = mock_redis.hset.call_args
        mapping = call_args[1]["mapping"]
        assert mapping["status"] == "processing"

    @pytest.mark.asyncio
    async def test_update_step_auto_progress(self, manager, mock_redis):
        await manager.update("test-123", step=TaskStep.ANALYZE)

        call_args = mock_redis.hset.call_args
        mapping = call_args[1]["mapping"]
        assert mapping["step"] == "analyze"
        assert mapping["progress"] == 50  # Auto-calculated

    @pytest.mark.asyncio
    async def test_get_existing(self, manager, mock_redis):
        mock_redis.hgetall.return_value = {
            "task_id": "test-123",
            "user_id": "user-456",
            "status": "processing",
            "step": "scan",
            "progress": "25",
            "partial_result": "{}",
            "metadata": "{}",
            "reward_status": "pending",
            "created_at": "2025-12-21T00:00:00Z",
            "updated_at": "2025-12-21T00:00:00Z",
        }

        state = await manager.get("test-123")

        assert state is not None
        assert state.task_id == "test-123"
        assert state.status == TaskStatus.PROCESSING

    @pytest.mark.asyncio
    async def test_get_not_found(self, manager, mock_redis):
        mock_redis.hgetall.return_value = {}

        state = await manager.get("nonexistent")

        assert state is None

    @pytest.mark.asyncio
    async def test_delete(self, manager, mock_redis):
        await manager.delete("test-123")

        mock_redis.delete.assert_called_once_with("task:test-123")

    @pytest.mark.asyncio
    async def test_close(self, manager, mock_redis):
        await manager.close()

        mock_redis.close.assert_called_once()
        assert manager._redis is None
