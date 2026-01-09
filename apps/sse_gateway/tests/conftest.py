"""SSE Gateway 테스트 설정."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# 모듈 경로 추가
sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture
def mock_redis_streams():
    """Redis Streams 클라이언트 Mock."""
    mock = AsyncMock()
    mock.get = AsyncMock(return_value=None)  # State KV 조회
    mock.close = AsyncMock()
    return mock


@pytest.fixture
def mock_redis_pubsub():
    """Redis Pub/Sub 클라이언트 Mock."""
    mock = AsyncMock()
    mock.pubsub = MagicMock()
    mock.close = AsyncMock()
    return mock


@pytest.fixture
def mock_settings():
    """Settings Mock."""
    mock = MagicMock()
    mock.service_name = "sse-gateway"
    mock.service_version = "1.0.0"
    mock.environment = "test"
    mock.redis_streams_url = "redis://localhost:6379/0"
    mock.redis_pubsub_url = "redis://localhost:6379/1"
    mock.redis_cache_url = "redis://localhost:6379/2"
    mock.pubsub_channel_prefix = "sse:events"
    mock.state_key_prefix = "scan:state"
    mock.state_timeout_seconds = 30
    mock.sse_keepalive_interval = 15.0
    mock.sse_max_wait_seconds = 300
    mock.sse_queue_maxsize = 100
    mock.log_level = "DEBUG"
    mock.otel_enabled = False
    mock.otel_sample_rate = 0.1
    return mock


@pytest.fixture
def reset_broadcast_manager():
    """테스트 간 BroadcastManager 싱글톤 초기화."""
    from core.broadcast_manager import SSEBroadcastManager

    # 테스트 전 초기화
    SSEBroadcastManager._instance = None

    yield

    # 테스트 후 정리
    if SSEBroadcastManager._instance is not None:
        asyncio.get_event_loop().run_until_complete(SSEBroadcastManager.shutdown())


@pytest.fixture
def client(mock_settings):
    """FastAPI TestClient fixture."""
    with patch("config.get_settings", return_value=mock_settings):
        with patch("main.get_settings", return_value=mock_settings):
            # get_instance는 async 함수이므로 AsyncMock 사용
            mock_instance = AsyncMock()
            mock_instance.active_job_count = 0
            mock_instance.total_subscriber_count = 0

            with patch(
                "core.broadcast_manager.SSEBroadcastManager.get_instance",
                new=AsyncMock(return_value=mock_instance),
            ):
                from fastapi.testclient import TestClient

                from main import app

                with TestClient(app) as test_client:
                    yield test_client
