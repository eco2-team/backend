"""ReadThroughCheckpointer 단위 테스트.

Redis hit, Redis miss + PG hit (promote), 양쪽 miss 시나리오 검증.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from langgraph.checkpoint.base import CheckpointTuple


@pytest.fixture
def mock_redis_saver():
    saver = AsyncMock()
    saver.aput = AsyncMock(return_value={"configurable": {"thread_id": "t1"}})
    saver.aput_no_sync = AsyncMock(return_value={"configurable": {"thread_id": "t1"}})
    saver.aput_writes = AsyncMock()
    return saver


@pytest.fixture
def mock_pg_saver():
    saver = AsyncMock()
    return saver


@pytest.fixture
def checkpointer(mock_redis_saver, mock_pg_saver):
    from chat_worker.infrastructure.orchestration.langgraph.sync import (
        ReadThroughCheckpointer,
    )

    return ReadThroughCheckpointer(
        redis_saver=mock_redis_saver,
        pg_saver=mock_pg_saver,
    )


@pytest.fixture
def sample_config():
    return {"configurable": {"thread_id": "session-123", "checkpoint_ns": ""}}


@pytest.fixture
def sample_checkpoint_tuple():
    return CheckpointTuple(
        config={"configurable": {"thread_id": "session-123", "checkpoint_ns": ""}},
        checkpoint={"v": 1, "id": "cp-1", "ts": "2026-01-24T00:00:00+00:00"},
        metadata={"source": "loop", "step": 3},
        pending_writes=[],
        parent_config=None,
    )


class TestRedisHit:
    """Redis에 checkpoint가 있는 경우 (hot path)."""

    async def test_returns_redis_result_directly(
        self, checkpointer, mock_redis_saver, mock_pg_saver, sample_config, sample_checkpoint_tuple
    ):
        mock_redis_saver.aget_tuple = AsyncMock(return_value=sample_checkpoint_tuple)

        result = await checkpointer.aget_tuple(sample_config)

        assert result == sample_checkpoint_tuple
        mock_redis_saver.aget_tuple.assert_awaited_once_with(sample_config)
        mock_pg_saver.aget_tuple.assert_not_awaited()

    async def test_no_promote_on_hit(
        self, checkpointer, mock_redis_saver, sample_config, sample_checkpoint_tuple
    ):
        mock_redis_saver.aget_tuple = AsyncMock(return_value=sample_checkpoint_tuple)

        await checkpointer.aget_tuple(sample_config)

        # aput_no_sync should not be called (no promote needed)
        mock_redis_saver.aput_no_sync.assert_not_awaited()
        assert checkpointer.get_stats()["promote_count"] == 0


class TestRedisMissPgHit:
    """Redis miss → PG hit → Redis promote (LRU write-back)."""

    async def test_promotes_to_redis(
        self, checkpointer, mock_redis_saver, mock_pg_saver, sample_config, sample_checkpoint_tuple
    ):
        mock_redis_saver.aget_tuple = AsyncMock(return_value=None)
        mock_pg_saver.aget_tuple = AsyncMock(return_value=sample_checkpoint_tuple)

        result = await checkpointer.aget_tuple(sample_config)

        assert result == sample_checkpoint_tuple
        # Should promote to Redis via aput_no_sync (bypass sync queue)
        mock_redis_saver.aput_no_sync.assert_awaited_once_with(
            config=sample_checkpoint_tuple.config,
            checkpoint=sample_checkpoint_tuple.checkpoint,
            metadata=sample_checkpoint_tuple.metadata,
            new_versions={},
        )
        assert checkpointer.get_stats()["promote_count"] == 1

    async def test_promotes_pending_writes(
        self, checkpointer, mock_redis_saver, mock_pg_saver, sample_config
    ):
        tuple_with_writes = CheckpointTuple(
            config={"configurable": {"thread_id": "session-123", "checkpoint_ns": ""}},
            checkpoint={"v": 1, "id": "cp-1", "ts": "2026-01-24T00:00:00+00:00"},
            metadata={"source": "loop", "step": 3},
            pending_writes=[("task-1", "messages", {"role": "user", "content": "hi"})],
            parent_config=None,
        )
        mock_redis_saver.aget_tuple = AsyncMock(return_value=None)
        mock_pg_saver.aget_tuple = AsyncMock(return_value=tuple_with_writes)

        await checkpointer.aget_tuple(sample_config)

        mock_redis_saver.aput_writes.assert_awaited_once_with(
            config=tuple_with_writes.config,
            writes=[("messages", {"role": "user", "content": "hi"})],
            task_id="task-1",
        )

    async def test_returns_pg_result_even_if_promote_fails(
        self, checkpointer, mock_redis_saver, mock_pg_saver, sample_config, sample_checkpoint_tuple
    ):
        mock_redis_saver.aget_tuple = AsyncMock(return_value=None)
        mock_redis_saver.aput_no_sync = AsyncMock(side_effect=Exception("Redis write error"))
        mock_pg_saver.aget_tuple = AsyncMock(return_value=sample_checkpoint_tuple)

        result = await checkpointer.aget_tuple(sample_config)

        # Should still return PG result despite promote failure
        assert result == sample_checkpoint_tuple
        assert checkpointer.get_stats()["promote_count"] == 0


class TestBothMiss:
    """Redis miss + PG miss (세션 존재하지 않음)."""

    async def test_returns_none(self, checkpointer, mock_redis_saver, mock_pg_saver, sample_config):
        mock_redis_saver.aget_tuple = AsyncMock(return_value=None)
        mock_pg_saver.aget_tuple = AsyncMock(return_value=None)

        result = await checkpointer.aget_tuple(sample_config)

        assert result is None
        assert checkpointer.get_stats()["miss_count"] == 1

    async def test_no_pg_saver(self, mock_redis_saver, sample_config):
        """PG saver가 None인 경우 (Redis-only 모드와 동일)."""
        from chat_worker.infrastructure.orchestration.langgraph.sync import (
            ReadThroughCheckpointer,
        )

        cp = ReadThroughCheckpointer(redis_saver=mock_redis_saver, pg_saver=None)
        mock_redis_saver.aget_tuple = AsyncMock(return_value=None)

        result = await cp.aget_tuple(sample_config)

        assert result is None


class TestWriteDelegation:
    """Write 연산은 SyncableRedisSaver에 위임."""

    async def test_aput_delegates(self, checkpointer, mock_redis_saver):
        config = {"configurable": {"thread_id": "t1"}}
        checkpoint = {"v": 1, "id": "cp-1"}
        metadata = {"source": "loop"}

        await checkpointer.aput(config, checkpoint, metadata, {})

        mock_redis_saver.aput.assert_awaited_once_with(config, checkpoint, metadata, {}, "values")

    async def test_aput_writes_delegates(self, checkpointer, mock_redis_saver):
        config = {"configurable": {"thread_id": "t1"}}
        writes = [("messages", {"role": "user"})]

        await checkpointer.aput_writes(config, writes, "task-1", "path")

        mock_redis_saver.aput_writes.assert_awaited_once_with(config, writes, "task-1", "path")


class TestAlist:
    """alist() 조회: Redis first, PG fallback."""

    async def test_returns_redis_results(
        self, checkpointer, mock_redis_saver, mock_pg_saver, sample_config, sample_checkpoint_tuple
    ):
        async def redis_alist(*args, **kwargs):
            yield sample_checkpoint_tuple

        mock_redis_saver.alist = redis_alist

        results = [item async for item in checkpointer.alist(sample_config)]

        assert results == [sample_checkpoint_tuple]

    async def test_falls_back_to_pg_when_redis_empty(
        self, checkpointer, mock_redis_saver, mock_pg_saver, sample_config, sample_checkpoint_tuple
    ):
        async def redis_alist_empty(*args, **kwargs):
            return
            yield  # noqa: make it an async generator

        async def pg_alist(*args, **kwargs):
            yield sample_checkpoint_tuple

        mock_redis_saver.alist = redis_alist_empty
        mock_pg_saver.alist = pg_alist

        results = [item async for item in checkpointer.alist(sample_config)]

        assert results == [sample_checkpoint_tuple]

    async def test_no_pg_fallback_when_redis_has_results(
        self, checkpointer, mock_redis_saver, mock_pg_saver, sample_config, sample_checkpoint_tuple
    ):
        async def redis_alist(*args, **kwargs):
            yield sample_checkpoint_tuple

        pg_called = False

        async def pg_alist(*args, **kwargs):
            nonlocal pg_called
            pg_called = True
            yield sample_checkpoint_tuple  # pragma: no cover

        mock_redis_saver.alist = redis_alist
        mock_pg_saver.alist = pg_alist

        results = [item async for item in checkpointer.alist(sample_config)]

        assert results == [sample_checkpoint_tuple]
        assert pg_called is False

    async def test_returns_empty_when_both_empty(
        self, checkpointer, mock_redis_saver, mock_pg_saver, sample_config
    ):
        async def empty_alist(*args, **kwargs):
            return
            yield  # noqa

        mock_redis_saver.alist = empty_alist
        mock_pg_saver.alist = empty_alist

        results = [item async for item in checkpointer.alist(sample_config)]

        assert results == []

    async def test_no_pg_fallback_when_pg_saver_none(self, mock_redis_saver, sample_config):
        from chat_worker.infrastructure.orchestration.langgraph.sync import (
            ReadThroughCheckpointer,
        )

        cp = ReadThroughCheckpointer(redis_saver=mock_redis_saver, pg_saver=None)

        async def empty_alist(*args, **kwargs):
            return
            yield  # noqa

        mock_redis_saver.alist = empty_alist

        results = [item async for item in cp.alist(sample_config)]

        assert results == []


class TestClose:
    """close() 리소스 정리."""

    async def test_closes_redis_saver(self, checkpointer, mock_redis_saver):
        mock_redis_saver.__aexit__ = AsyncMock()

        await checkpointer.close()

        mock_redis_saver.__aexit__.assert_awaited_once_with(None, None, None)

    async def test_closes_pg_pool(self, checkpointer, mock_pg_saver):
        mock_pool = AsyncMock()
        mock_pg_saver.conn = mock_pool

        await checkpointer.close()

        mock_pool.close.assert_awaited_once()

    async def test_handles_no_aexit_on_redis(self, mock_pg_saver):
        from chat_worker.infrastructure.orchestration.langgraph.sync import (
            ReadThroughCheckpointer,
        )

        redis_saver = AsyncMock(spec=[])  # no __aexit__
        cp = ReadThroughCheckpointer(redis_saver=redis_saver, pg_saver=mock_pg_saver)

        # Should not raise
        await cp.close()

    async def test_handles_no_conn_on_pg(self, mock_redis_saver):
        from chat_worker.infrastructure.orchestration.langgraph.sync import (
            ReadThroughCheckpointer,
        )

        pg_saver = AsyncMock(spec=[])  # no .conn
        cp = ReadThroughCheckpointer(redis_saver=mock_redis_saver, pg_saver=pg_saver)

        # Should not raise
        await cp.close()

    async def test_handles_pg_saver_none(self, mock_redis_saver):
        from chat_worker.infrastructure.orchestration.langgraph.sync import (
            ReadThroughCheckpointer,
        )

        cp = ReadThroughCheckpointer(redis_saver=mock_redis_saver, pg_saver=None)

        # Should not raise
        await cp.close()


class TestStats:
    """통계 추적 검증."""

    async def test_stats_accumulate(
        self, checkpointer, mock_redis_saver, mock_pg_saver, sample_config, sample_checkpoint_tuple
    ):
        # 1 promote
        mock_redis_saver.aget_tuple = AsyncMock(return_value=None)
        mock_pg_saver.aget_tuple = AsyncMock(return_value=sample_checkpoint_tuple)
        await checkpointer.aget_tuple(sample_config)

        # 1 miss
        mock_pg_saver.aget_tuple = AsyncMock(return_value=None)
        await checkpointer.aget_tuple(sample_config)

        stats = checkpointer.get_stats()
        assert stats["promote_count"] == 1
        assert stats["miss_count"] == 1
