"""auth_worker 테스트 공통 Fixtures."""

from __future__ import annotations

import sys
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def sample_blacklist_data() -> dict[str, Any]:
    """블랙리스트 이벤트 샘플 데이터."""
    return {
        "type": "add",
        "jti": "test-jti-12345678",
        "expires_at": "2025-12-31T23:59:59+00:00",
        "timestamp": "2025-01-01T00:00:00+00:00",
        "user_id": "user-123",
        "reason": "logout",
    }


@pytest.fixture
def sample_blacklist_data_minimal() -> dict[str, Any]:
    """최소 필드만 포함된 블랙리스트 이벤트."""
    return {
        "type": "add",
        "jti": "test-jti-minimal",
        "expires_at": "2025-12-31T23:59:59+00:00",
        "timestamp": "2025-01-01T00:00:00+00:00",
    }


@pytest.fixture
def mock_redis() -> AsyncMock:
    """Mock Redis 클라이언트."""
    redis = AsyncMock()
    redis.setex = AsyncMock()
    redis.delete = AsyncMock()
    redis.exists = AsyncMock(return_value=0)
    return redis


@pytest.fixture
def mock_blacklist_store() -> AsyncMock:
    """Mock BlacklistStore."""
    store = AsyncMock()
    store.add = AsyncMock()
    store.remove = AsyncMock()
    store.contains = AsyncMock(return_value=False)
    return store


@pytest.fixture
def mock_message() -> MagicMock:
    """Mock RabbitMQ 메시지."""
    message = MagicMock()
    message.ack = AsyncMock()
    message.nack = AsyncMock()
    return message
