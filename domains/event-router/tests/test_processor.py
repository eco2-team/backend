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
    def mock_streams_redis(self):
        """Mock Streams Redis 클라이언트."""
        mock = AsyncMock()
        mock.register_script = lambda script: AsyncMock(return_value=1)
        return mock

    @pytest.fixture
    def mock_pubsub_redis(self):
        """Mock Pub/Sub Redis 클라이언트."""
        mock = AsyncMock()
        mock.publish = AsyncMock()
        return mock

    @pytest.fixture
    def processor(self, mock_streams_redis, mock_pubsub_redis):
        """EventProcessor 인스턴스."""
        from core.processor import EventProcessor

        return EventProcessor(
            streams_client=mock_streams_redis,
            pubsub_client=mock_pubsub_redis,
        )

    def test_processor_initialization(self, processor):
        """프로세서 초기화 확인."""
        assert processor._state_key_prefix == "scan:state"
        assert processor._published_key_prefix == "router:published"
        assert processor._pubsub_channel_prefix == "sse:events"
        assert processor._state_ttl == 3600
        assert processor._published_ttl == 7200

    @pytest.mark.asyncio
    async def test_process_event_missing_job_id(self, processor):
        """job_id 없는 이벤트 스킵."""
        event = {"stage": "vision", "status": "success"}
        result = await processor.process_event(event)
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
