"""Event Router 테스트 설정."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# 모듈 경로 추가
sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture
def mock_settings():
    """Settings Mock."""
    mock = MagicMock()
    mock.service_name = "event-router"
    mock.service_version = "1.0.0"
    mock.environment = "test"
    mock.redis_streams_url = "redis://localhost:6379/0"
    mock.redis_pubsub_url = "redis://localhost:6379/1"
    mock.consumer_group = "eventrouter"
    mock.consumer_name = "consumer-0"
    mock.shard_count = 4
    mock.stream_prefix = "scan:events"
    mock.pubsub_channel_prefix = "sse:events"
    mock.state_key_prefix = "scan:state"
    mock.router_published_prefix = "router:published"
    mock.xread_block_ms = 5000
    mock.xread_count = 100
    mock.reclaim_interval_seconds = 30
    mock.reclaim_min_idle_ms = 60000
    mock.state_ttl = 3600
    mock.published_ttl = 7200
    mock.log_level = "DEBUG"
    return mock
