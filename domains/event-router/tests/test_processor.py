"""Processor 모듈 테스트."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestEventProcessor:
    """EventProcessor 클래스 테스트."""

    @pytest.fixture
    def mock_redis(self):
        """Mock Redis 클라이언트."""
        mock = AsyncMock()
        return mock

    @pytest.fixture
    def processor(self, mock_redis):
        """EventProcessor 인스턴스."""
        from core.processor import EventProcessor

        return EventProcessor(redis_client=mock_redis)

    def test_processor_initialization(self, processor):
        """프로세서 초기화 확인."""
        assert processor._state_key_prefix == "scan:state"
        assert processor._published_key_prefix == "router:published"
        assert processor._pubsub_channel_prefix == "sse:events"
        assert processor._state_ttl == 3600
        assert processor._published_ttl == 7200

    @pytest.mark.asyncio
    async def test_process_event_new(self, processor, mock_redis):
        """새 이벤트 처리."""
        # Lua 스크립트 실행 결과 mock
        mock_redis.evalsha = AsyncMock(return_value=[1, "published"])  # 새로 발행

        event_data = {
            "job_id": "test-job-123",
            "stage": "vision",
            "status": "success",
            "seq": 1,
            "ts": "2025-01-01T00:00:00",
        }

        result = await processor.process_event(
            stream_key="scan:events:0",
            message_id="1234567890-0",
            event_data=event_data,
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_process_event_duplicate(self, processor, mock_redis):
        """중복 이벤트 스킵."""
        # Lua 스크립트 실행 결과 mock - 이미 발행됨
        mock_redis.evalsha = AsyncMock(return_value=[0, "already_published"])

        event_data = {
            "job_id": "test-job-123",
            "stage": "vision",
            "status": "success",
            "seq": 1,
            "ts": "2025-01-01T00:00:00",
        }

        result = await processor.process_event(
            stream_key="scan:events:0",
            message_id="1234567890-0",
            event_data=event_data,
        )

        # 중복이어도 True 반환 (XACK 해야 하므로)
        assert result is True

    @pytest.mark.asyncio
    async def test_process_event_error(self, processor, mock_redis):
        """이벤트 처리 에러."""
        mock_redis.evalsha = AsyncMock(side_effect=Exception("Redis error"))

        event_data = {
            "job_id": "test-job-123",
            "stage": "vision",
            "status": "success",
            "seq": 1,
        }

        result = await processor.process_event(
            stream_key="scan:events:0",
            message_id="1234567890-0",
            event_data=event_data,
        )

        assert result is False


class TestStateSnapshot:
    """State 스냅샷 생성 테스트."""

    def test_create_state_snapshot(self):
        """State 스냅샷 생성."""
        event_data = {
            "job_id": "test-job",
            "stage": "vision",
            "status": "success",
            "seq": 1,
            "progress": 25,
            "result": {"classification": "recyclable"},
        }

        # State 스냅샷은 이벤트 데이터와 동일 구조
        state = json.dumps(event_data)
        parsed = json.loads(state)

        assert parsed["job_id"] == "test-job"
        assert parsed["stage"] == "vision"
        assert parsed["seq"] == 1
