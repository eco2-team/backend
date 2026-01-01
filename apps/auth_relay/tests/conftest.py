"""Test fixtures for auth_relay."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock

import pytest


@pytest.fixture
def sample_event_data() -> dict[str, Any]:
    """Sample blacklist event data."""
    return {
        "jti": "abc123def456",
        "type": "access",
        "exp": 1704067200,
        "user_id": 42,
    }


@pytest.fixture
def sample_event_json(sample_event_data: dict[str, Any]) -> str:
    """Sample event JSON string."""
    return json.dumps(sample_event_data)


@pytest.fixture
def mock_redis() -> AsyncMock:
    """Mock Redis client."""
    redis = AsyncMock()
    redis.rpop = AsyncMock(return_value=None)
    redis.lpush = AsyncMock()
    redis.llen = AsyncMock(return_value=0)
    redis.ping = AsyncMock()
    redis.close = AsyncMock()
    return redis


@pytest.fixture
def mock_publisher() -> AsyncMock:
    """Mock event publisher."""
    publisher = AsyncMock()
    publisher.connect = AsyncMock()
    publisher.close = AsyncMock()
    publisher.publish = AsyncMock()
    return publisher


@pytest.fixture
def mock_outbox_reader() -> AsyncMock:
    """Mock outbox reader."""
    reader = AsyncMock()
    reader.pop = AsyncMock(return_value=None)
    reader.push_back = AsyncMock()
    reader.push_to_dlq = AsyncMock()
    reader.length = AsyncMock(return_value=0)
    return reader


@pytest.fixture
def mock_relay_command() -> AsyncMock:
    """Mock relay command."""
    from apps.auth_relay.application.common.result import RelayResult

    command = AsyncMock()
    command.execute = AsyncMock(return_value=RelayResult.success())
    return command
