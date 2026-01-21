"""BroadcastManager 테스트."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

# apps/ 디렉토리를 PYTHONPATH에 추가 (from sse_gateway.* 가능하게)
APPS_DIR = Path(__file__).resolve().parents[2]
if str(APPS_DIR) not in sys.path:
    sys.path.insert(0, str(APPS_DIR))


class TestSubscriberQueue:
    """SubscriberQueue 테스트."""

    @pytest.mark.asyncio
    async def test_put_event_success(self):
        """이벤트 추가 성공."""
        from sse_gateway.core.broadcast_manager import SubscriberQueue

        queue = SubscriberQueue(job_id="test-job")
        event = {"stage": "vision", "status": "success", "seq": 1}

        result = await queue.put_event(event)

        assert result is True
        assert queue.queue.qsize() == 1

    @pytest.mark.asyncio
    async def test_put_event_updates_timestamp(self):
        """이벤트 추가 시 타임스탬프 업데이트."""

        from sse_gateway.core.broadcast_manager import SubscriberQueue

        queue = SubscriberQueue(job_id="test-job")
        initial_time = queue.last_event_at

        await asyncio.sleep(0.01)
        await queue.put_event({"stage": "vision", "seq": 1})

        assert queue.last_event_at > initial_time

    @pytest.mark.asyncio
    async def test_put_event_duplicate_seq_rejected(self):
        """중복 timestamp 이벤트 거부 (timestamp 기반 필터링)."""
        from sse_gateway.core.broadcast_manager import SubscriberQueue

        queue = SubscriberQueue(job_id="test-job")

        # 첫 번째 이벤트 성공
        result1 = await queue.put_event(
            {"stage": "vision", "status": "started", "timestamp": 1000.0, "seq": 1}
        )
        assert result1 is True

        # 같은 stage:status의 같은 timestamp 거부
        result2 = await queue.put_event(
            {"stage": "vision", "status": "started", "timestamp": 1000.0, "seq": 1}
        )
        assert result2 is False

        # 같은 stage:status의 더 오래된 timestamp 거부
        result3 = await queue.put_event(
            {"stage": "vision", "status": "started", "timestamp": 999.0, "seq": 0}
        )
        assert result3 is False

        # 더 최근 timestamp는 성공
        result4 = await queue.put_event(
            {"stage": "vision", "status": "started", "timestamp": 1001.0, "seq": 2}
        )
        assert result4 is True

        # 다른 stage는 seq 무관하게 성공 (timestamp 기반)
        result5 = await queue.put_event(
            {"stage": "rule", "status": "started", "timestamp": 500.0, "seq": 0}
        )
        assert result5 is True

        assert queue.queue.qsize() == 3  # vision(1000), vision(1001), rule(500)

    @pytest.mark.asyncio
    async def test_put_event_preserves_done(self):
        """done 이벤트는 드롭되지 않음."""
        from sse_gateway.core.broadcast_manager import SubscriberQueue

        queue = SubscriberQueue(job_id="test-job")
        queue.queue = asyncio.Queue(maxsize=2)

        # done 이벤트로 Queue 채우기 (timestamp 필수)
        await queue.put_event({"stage": "done", "status": "started", "timestamp": 1000.0, "seq": 1})
        await queue.put_event(
            {"stage": "done", "status": "completed", "timestamp": 1001.0, "seq": 2}
        )

        # 새 이벤트는 done을 보존하므로 드롭
        result = await queue.put_event(
            {"stage": "vision", "status": "started", "timestamp": 1002.0, "seq": 3}
        )
        assert result is False

        # done이 유지됨
        assert queue.queue.qsize() == 2


class TestSSEBroadcastManager:
    """SSEBroadcastManager 테스트."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """테스트 간 싱글톤 초기화."""
        from sse_gateway.core.broadcast_manager import SSEBroadcastManager

        SSEBroadcastManager._instance = None
        yield
        SSEBroadcastManager._instance = None

    def test_total_subscriber_count_empty(self):
        """구독자 없을 때 카운트."""
        from sse_gateway.core.broadcast_manager import SSEBroadcastManager

        manager = SSEBroadcastManager()
        assert manager._total_subscriber_count() == 0

    def test_active_job_count(self):
        """활성 job 카운트."""
        from sse_gateway.core.broadcast_manager import SSEBroadcastManager

        manager = SSEBroadcastManager()

        # _subscribers는 job_id -> set 매핑
        manager._subscribers["job-1"] = set()
        manager._subscribers["job-2"] = set()

        # active_job_count는 _subscribers의 키 수
        assert manager.active_job_count == 2
        # 빈 set이므로 total_subscriber_count는 0
        assert manager.total_subscriber_count == 0

    @pytest.mark.asyncio
    async def test_get_state_snapshot_no_client(self):
        """Streams 클라이언트 없을 때 스냅샷 조회."""
        from sse_gateway.core.broadcast_manager import SSEBroadcastManager

        manager = SSEBroadcastManager()
        manager._streams_client = None

        result = await manager._get_state_snapshot("test-job")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_state_snapshot_cache_miss(self):
        """캐시 미스 시 None 반환."""
        from sse_gateway.core.broadcast_manager import SSEBroadcastManager

        manager = SSEBroadcastManager()
        mock_streams = AsyncMock()
        mock_streams.get = AsyncMock(return_value=None)
        manager._streams_client = mock_streams

        result = await manager._get_state_snapshot("test-job")

        assert result is None
        mock_streams.get.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_state_snapshot_cache_hit(self):
        """캐시 히트 시 데이터 반환."""
        from sse_gateway.core.broadcast_manager import SSEBroadcastManager

        manager = SSEBroadcastManager()
        mock_streams = AsyncMock()
        snapshot_data = {"stage": "vision", "status": "success", "seq": 1}
        mock_streams.get = AsyncMock(return_value=json.dumps(snapshot_data))
        manager._streams_client = mock_streams

        result = await manager._get_state_snapshot("test-job")

        assert result == snapshot_data

    @pytest.mark.asyncio
    async def test_get_state_snapshot_error(self):
        """Redis 오류 시 None 반환."""
        from sse_gateway.core.broadcast_manager import SSEBroadcastManager

        manager = SSEBroadcastManager()
        mock_streams = AsyncMock()
        mock_streams.get = AsyncMock(side_effect=Exception("Redis error"))
        manager._streams_client = mock_streams

        result = await manager._get_state_snapshot("test-job")

        assert result is None

    @pytest.mark.asyncio
    async def test_shutdown_cleans_up(self):
        """shutdown 시 리소스 정리."""
        from sse_gateway.core.broadcast_manager import SSEBroadcastManager

        # 인스턴스 생성
        SSEBroadcastManager._instance = SSEBroadcastManager()
        manager = SSEBroadcastManager._instance

        # Mock 클라이언트 설정
        mock_streams = AsyncMock()
        mock_pubsub = AsyncMock()

        manager._streams_client = mock_streams
        manager._pubsub_client = mock_pubsub
        manager._pubsub_tasks = {}

        # shutdown 호출
        await SSEBroadcastManager.shutdown()

        # 정리 확인
        assert SSEBroadcastManager._instance is None
        mock_streams.close.assert_called_once()
        mock_pubsub.close.assert_called_once()
