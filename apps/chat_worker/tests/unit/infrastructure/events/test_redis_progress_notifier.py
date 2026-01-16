"""RedisProgressNotifier 단위 테스트.

Lua Script 기반 멱등성 발행 테스트.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from chat_worker.infrastructure.events.redis_progress_notifier import (
    RedisProgressNotifier,
    _get_shard_for_job,
    _get_stream_key,
)


class TestShardFunctions:
    """Shard 관련 함수 테스트."""

    def test_get_shard_for_job_consistent(self):
        """같은 job_id는 항상 같은 shard."""
        job_id = "test-job-123"
        shard1 = _get_shard_for_job(job_id, shard_count=4)
        shard2 = _get_shard_for_job(job_id, shard_count=4)
        assert shard1 == shard2

    def test_get_shard_for_job_distribution(self):
        """여러 job_id가 여러 shard에 분산."""
        shards = set()
        for i in range(100):
            shard = _get_shard_for_job(f"job-{i}", shard_count=4)
            shards.add(shard)

        # 100개 job_id면 4개 shard 모두 사용될 가능성 높음
        assert len(shards) >= 2

    def test_get_shard_for_job_within_range(self):
        """Shard 번호가 범위 내."""
        for i in range(50):
            shard = _get_shard_for_job(f"job-{i}", shard_count=4)
            assert 0 <= shard < 4

    def test_get_stream_key_format(self):
        """Stream key 형식."""
        key = _get_stream_key("job-123", shard_count=4)
        assert key.startswith("chat:events:")
        assert key.split(":")[-1].isdigit()


class TestRedisProgressNotifier:
    """RedisProgressNotifier 테스트 스위트."""

    @pytest.fixture
    def mock_redis(self) -> AsyncMock:
        """Mock Redis 클라이언트."""
        redis = AsyncMock()

        # Lua Script mock - 호출 시 coroutine 반환
        async def mock_stage_script(*args, **kwargs):
            return [1, b"1234567890-0"]

        async def mock_token_script(*args, **kwargs):
            return b"1234567890-0"

        stage_script = MagicMock()
        stage_script.side_effect = mock_stage_script

        token_script = MagicMock()
        token_script.side_effect = mock_token_script

        # register_script가 호출될 때마다 다른 mock 반환
        script_mocks = [stage_script, token_script]
        script_index = [0]

        def get_script(lua_code):
            idx = script_index[0]
            script_index[0] = (idx + 1) % 2
            return script_mocks[idx]

        redis.register_script = MagicMock(side_effect=get_script)

        return redis

    @pytest.fixture
    def notifier(self, mock_redis: AsyncMock) -> RedisProgressNotifier:
        """테스트용 Notifier."""
        return RedisProgressNotifier(
            redis=mock_redis,
            shard_count=4,
            maxlen=500,
        )

    # ==========================================================
    # notify_stage Tests
    # ==========================================================

    @pytest.mark.asyncio
    async def test_notify_stage_basic(
        self,
        notifier: RedisProgressNotifier,
        mock_redis: AsyncMock,
    ):
        """기본 단계 알림."""
        event_id = await notifier.notify_stage(
            task_id="job-123",
            stage="intent",
            status="started",
        )

        assert event_id is not None
        # Lua script 등록 확인
        assert mock_redis.register_script.called

    @pytest.mark.asyncio
    async def test_notify_stage_with_progress(
        self,
        notifier: RedisProgressNotifier,
        mock_redis: AsyncMock,
    ):
        """진행률 포함 알림."""
        event_id = await notifier.notify_stage(
            task_id="job-123",
            stage="rag",
            status="processing",
            progress=50,
            message="규정 검색 중...",
        )

        assert event_id is not None

    @pytest.mark.asyncio
    async def test_notify_stage_with_result(
        self,
        notifier: RedisProgressNotifier,
        mock_redis: AsyncMock,
    ):
        """결과 포함 알림."""
        event_id = await notifier.notify_stage(
            task_id="job-123",
            stage="intent",
            status="completed",
            result={"intent": "waste", "confidence": 0.95},
        )

        assert event_id is not None

    @pytest.mark.asyncio
    async def test_notify_stage_returns_event_id(
        self,
        notifier: RedisProgressNotifier,
        mock_redis: AsyncMock,
    ):
        """이벤트 ID 반환 확인."""
        event_id = await notifier.notify_stage(
            task_id="job-123",
            stage="intent",
            status="started",
        )

        # b"1234567890-0" -> "1234567890-0"
        assert "1234567890-0" in event_id

    # ==========================================================
    # notify_token Tests
    # ==========================================================

    @pytest.mark.asyncio
    async def test_notify_token(
        self,
        notifier: RedisProgressNotifier,
        mock_redis: AsyncMock,
    ):
        """토큰 스트리밍 알림."""
        event_id = await notifier.notify_token(
            task_id="job-456",
            content="안녕",
        )

        assert event_id is not None

    @pytest.mark.asyncio
    async def test_notify_token_multiple(
        self,
        notifier: RedisProgressNotifier,
        mock_redis: AsyncMock,
    ):
        """여러 토큰 연속 알림."""
        tokens = ["안녕", "하세요", "!"]

        for token in tokens:
            event_id = await notifier.notify_token(task_id="job-789", content=token)
            assert event_id is not None

    @pytest.mark.asyncio
    async def test_notify_token_seq_increments(
        self,
        notifier: RedisProgressNotifier,
        mock_redis: AsyncMock,
    ):
        """토큰 seq가 증가하는지 확인."""
        # 내부 _token_seq 딕셔너리 확인
        await notifier.notify_token(task_id="job-seq", content="a")
        await notifier.notify_token(task_id="job-seq", content="b")
        await notifier.notify_token(task_id="job-seq", content="c")

        # 3번 호출 후 seq는 1003 (1000 + 3)
        assert notifier._token_seq.get("job-seq", 0) == 1003

    # ==========================================================
    # notify_needs_input Tests
    # ==========================================================

    @pytest.mark.asyncio
    async def test_notify_needs_input(
        self,
        notifier: RedisProgressNotifier,
        mock_redis: AsyncMock,
    ):
        """입력 요청 알림."""
        event_id = await notifier.notify_needs_input(
            task_id="job-abc",
            input_type="location",
            message="위치 정보를 입력해주세요.",
            timeout=60,
        )

        assert event_id is not None

    @pytest.mark.asyncio
    async def test_notify_needs_input_default_timeout(
        self,
        notifier: RedisProgressNotifier,
        mock_redis: AsyncMock,
    ):
        """기본 타임아웃."""
        event_id = await notifier.notify_needs_input(
            task_id="job-def",
            input_type="confirmation",
            message="계속할까요?",
        )

        assert event_id is not None

    # ==========================================================
    # Shard Tests
    # ==========================================================

    @pytest.mark.asyncio
    async def test_same_job_same_shard(
        self,
        notifier: RedisProgressNotifier,
        mock_redis: AsyncMock,
    ):
        """같은 job_id는 같은 shard로."""
        job_id = "consistent-job"

        # 여러 번 호출해도 같은 shard
        shard1 = _get_shard_for_job(job_id, shard_count=4)
        shard2 = _get_shard_for_job(job_id, shard_count=4)

        assert shard1 == shard2

    @pytest.mark.asyncio
    async def test_different_jobs_may_different_shards(
        self,
        notifier: RedisProgressNotifier,
        mock_redis: AsyncMock,
    ):
        """다른 job_id는 다른 shard일 수 있음."""
        shards = set()
        for i in range(20):
            shard = _get_shard_for_job(f"job-{i}", shard_count=4)
            shards.add(shard)

        # 20개 job_id면 여러 shard에 분산
        assert len(shards) >= 2
