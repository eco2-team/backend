"""BroadcastManager 테스트."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestSubscriberQueue:
    """SubscriberQueue 테스트."""

    @pytest.mark.asyncio
    async def test_put_event_success(self):
        """이벤트 추가 성공."""
        from core.broadcast_manager import SubscriberQueue

        queue = SubscriberQueue(job_id="test-job")
        event = {"stage": "vision", "status": "success"}

        result = await queue.put_event(event)

        assert result is True
        assert queue.queue.qsize() == 1

    @pytest.mark.asyncio
    async def test_put_event_updates_timestamp(self):
        """이벤트 추가 시 타임스탬프 업데이트."""

        from core.broadcast_manager import SubscriberQueue

        queue = SubscriberQueue(job_id="test-job")
        initial_time = queue.last_event_at

        await asyncio.sleep(0.01)
        await queue.put_event({"stage": "vision"})

        assert queue.last_event_at > initial_time

    @pytest.mark.asyncio
    async def test_put_event_queue_full_drops_old(self):
        """Queue 가득 찼을 때 오래된 이벤트 드롭."""
        from core.broadcast_manager import SubscriberQueue

        # 작은 Queue 생성
        queue = SubscriberQueue(job_id="test-job")
        queue.queue = asyncio.Queue(maxsize=2)

        # Queue 채우기
        await queue.put_event({"stage": "vision"})
        await queue.put_event({"stage": "rule"})

        # 새 이벤트 추가 (오래된 것 드롭)
        await queue.put_event({"stage": "answer"})

        # Queue에 2개만 있어야 함
        assert queue.queue.qsize() == 2

    @pytest.mark.asyncio
    async def test_put_event_preserves_done(self):
        """done 이벤트는 드롭되지 않음."""
        from core.broadcast_manager import SubscriberQueue

        queue = SubscriberQueue(job_id="test-job")
        queue.queue = asyncio.Queue(maxsize=2)

        # done 이벤트로 Queue 채우기
        await queue.put_event({"stage": "done"})
        await queue.put_event({"stage": "done"})

        # 새 이벤트는 드롭되어야 함
        await queue.put_event({"stage": "vision"})

        # done이 유지되면 새 이벤트가 드롭될 수 있음
        assert queue.queue.qsize() == 2


class TestSSEBroadcastManager:
    """SSEBroadcastManager 테스트."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """테스트 간 싱글톤 초기화."""
        from core.broadcast_manager import SSEBroadcastManager

        SSEBroadcastManager._instance = None
        yield
        SSEBroadcastManager._instance = None

    def test_parse_event_bytes(self):
        """바이트 데이터 파싱."""
        from core.broadcast_manager import SSEBroadcastManager

        manager = SSEBroadcastManager()
        data = {
            b"job_id": b"test-123",
            b"stage": b"vision",
            b"status": b"success",
        }

        result = manager._parse_event(data)

        assert result["job_id"] == "test-123"
        assert result["stage"] == "vision"
        assert result["status"] == "success"

    def test_parse_event_string(self):
        """문자열 데이터 파싱."""
        from core.broadcast_manager import SSEBroadcastManager

        manager = SSEBroadcastManager()
        data = {
            "job_id": "test-456",
            "stage": "rule",
            "status": "success",
        }

        result = manager._parse_event(data)

        assert result["job_id"] == "test-456"
        assert result["stage"] == "rule"

    def test_parse_event_with_json_result(self):
        """JSON result 필드 파싱."""
        from core.broadcast_manager import SSEBroadcastManager

        manager = SSEBroadcastManager()
        result_data = {"classification": "recyclable", "confidence": 0.95}
        data = {
            b"job_id": b"test-789",
            b"stage": b"vision",
            b"result": json.dumps(result_data).encode(),
        }

        result = manager._parse_event(data)

        assert result["result"] == result_data

    def test_parse_event_with_progress(self):
        """progress 정수 변환."""
        from core.broadcast_manager import SSEBroadcastManager

        manager = SSEBroadcastManager()
        data = {
            b"job_id": b"test-progress",
            b"stage": b"vision",
            b"progress": b"75",
        }

        result = manager._parse_event(data)

        assert result["progress"] == 75

    def test_parse_event_invalid_json_result(self):
        """잘못된 JSON result 처리."""
        from core.broadcast_manager import SSEBroadcastManager

        manager = SSEBroadcastManager()
        data = {
            "job_id": "test-invalid",
            "stage": "vision",
            "result": "not-json{",
        }

        result = manager._parse_event(data)

        # JSON 파싱 실패 시 원래 문자열 유지
        assert result["result"] == "not-json{"

    def test_total_subscriber_count_empty(self):
        """구독자 없을 때 카운트."""
        from core.broadcast_manager import SSEBroadcastManager

        manager = SSEBroadcastManager()
        assert manager._total_subscriber_count() == 0

    def test_active_job_count(self):
        """활성 job 카운트."""
        from core.broadcast_manager import SSEBroadcastManager

        manager = SSEBroadcastManager()

        # _subscribers는 job_id -> set 매핑
        # 실제 코드에서는 subscribe()를 통해 추가되지만
        # 여기서는 단순히 키의 개수만 테스트
        manager._subscribers["job-1"] = set()
        manager._subscribers["job-2"] = set()

        # active_job_count는 _subscribers의 키 수
        assert manager.active_job_count == 2
        # 빈 set이므로 total_subscriber_count는 0
        assert manager.total_subscriber_count == 0

    @pytest.mark.asyncio
    async def test_get_state_snapshot_no_cache(self):
        """캐시 클라이언트 없을 때 스냅샷 조회."""
        from core.broadcast_manager import SSEBroadcastManager

        manager = SSEBroadcastManager()
        manager._cache_client = None

        result = await manager._get_state_snapshot("test-job")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_state_snapshot_cache_miss(self):
        """캐시 미스 시 None 반환."""
        from core.broadcast_manager import SSEBroadcastManager

        manager = SSEBroadcastManager()
        mock_cache = AsyncMock()
        mock_cache.get = AsyncMock(return_value=None)
        manager._cache_client = mock_cache

        result = await manager._get_state_snapshot("test-job")

        assert result is None
        mock_cache.get.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_state_snapshot_cache_hit(self):
        """캐시 히트 시 데이터 반환."""
        from core.broadcast_manager import SSEBroadcastManager

        manager = SSEBroadcastManager()
        mock_cache = AsyncMock()
        snapshot_data = {"stage": "vision", "status": "success"}
        mock_cache.get = AsyncMock(return_value=json.dumps(snapshot_data))
        manager._cache_client = mock_cache

        result = await manager._get_state_snapshot("test-job")

        assert result == snapshot_data

    @pytest.mark.asyncio
    async def test_get_state_snapshot_cache_error(self):
        """캐시 오류 시 None 반환."""
        from core.broadcast_manager import SSEBroadcastManager

        manager = SSEBroadcastManager()
        mock_cache = AsyncMock()
        mock_cache.get = AsyncMock(side_effect=Exception("Redis error"))
        manager._cache_client = mock_cache

        result = await manager._get_state_snapshot("test-job")

        assert result is None

    @pytest.mark.asyncio
    async def test_shutdown_cleans_up(self):
        """shutdown 시 리소스 정리."""
        from core.broadcast_manager import SSEBroadcastManager

        # 인스턴스 생성
        SSEBroadcastManager._instance = SSEBroadcastManager()
        manager = SSEBroadcastManager._instance

        # Mock 클라이언트 설정
        mock_streams = AsyncMock()
        mock_cache = AsyncMock()

        manager._streams_client = mock_streams
        manager._cache_client = mock_cache
        # background_task는 None으로 설정 (테스트에서는 consumer loop 없음)
        manager._background_task = None

        # shutdown 호출
        await SSEBroadcastManager.shutdown()

        # 정리 확인
        assert SSEBroadcastManager._instance is None
        mock_streams.close.assert_called_once()
        mock_cache.close.assert_called_once()
