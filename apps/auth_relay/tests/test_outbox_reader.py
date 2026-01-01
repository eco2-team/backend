"""Tests for RedisOutboxReader."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from apps.auth_relay.infrastructure.persistence_redis.outbox_reader_redis import (
    RedisOutboxReader,
)


class TestRedisOutboxReader:
    """RedisOutboxReader tests."""

    @pytest.fixture
    def reader(self, mock_redis: AsyncMock) -> RedisOutboxReader:
        """Create reader with mock redis."""
        return RedisOutboxReader(mock_redis)

    @pytest.mark.asyncio
    async def test_pop_returns_string(
        self,
        reader: RedisOutboxReader,
        mock_redis: AsyncMock,
    ) -> None:
        """pop() should return string from redis."""
        mock_redis.rpop.return_value = '{"jti": "abc"}'

        result = await reader.pop()

        assert result == '{"jti": "abc"}'
        mock_redis.rpop.assert_called_once_with(RedisOutboxReader.OUTBOX_KEY)

    @pytest.mark.asyncio
    async def test_pop_returns_none_when_empty(
        self,
        reader: RedisOutboxReader,
        mock_redis: AsyncMock,
    ) -> None:
        """pop() should return None when queue is empty."""
        mock_redis.rpop.return_value = None

        result = await reader.pop()

        assert result is None

    @pytest.mark.asyncio
    async def test_pop_decodes_bytes(
        self,
        reader: RedisOutboxReader,
        mock_redis: AsyncMock,
    ) -> None:
        """pop() should decode bytes to string."""
        mock_redis.rpop.return_value = b'{"jti": "abc"}'

        result = await reader.pop()

        assert result == '{"jti": "abc"}'

    @pytest.mark.asyncio
    async def test_push_back(
        self,
        reader: RedisOutboxReader,
        mock_redis: AsyncMock,
    ) -> None:
        """push_back() should LPUSH to outbox."""
        await reader.push_back('{"jti": "abc"}')

        mock_redis.lpush.assert_called_once_with(RedisOutboxReader.OUTBOX_KEY, '{"jti": "abc"}')

    @pytest.mark.asyncio
    async def test_push_to_dlq(
        self,
        reader: RedisOutboxReader,
        mock_redis: AsyncMock,
    ) -> None:
        """push_to_dlq() should LPUSH to DLQ."""
        await reader.push_to_dlq('{"jti": "abc"}')

        mock_redis.lpush.assert_called_once_with(RedisOutboxReader.DLQ_KEY, '{"jti": "abc"}')

    @pytest.mark.asyncio
    async def test_length(
        self,
        reader: RedisOutboxReader,
        mock_redis: AsyncMock,
    ) -> None:
        """length() should return queue length."""
        mock_redis.llen.return_value = 5

        result = await reader.length()

        assert result == 5
        mock_redis.llen.assert_called_once_with(RedisOutboxReader.OUTBOX_KEY)

    def test_key_constants(self) -> None:
        """Should have correct key constants."""
        assert RedisOutboxReader.OUTBOX_KEY == "outbox:blacklist"
        assert RedisOutboxReader.DLQ_KEY == "outbox:blacklist:dlq"
