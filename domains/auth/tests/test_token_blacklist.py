"""Tests for token_blacklist module."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from domains.auth.application.services.token_blacklist import TokenBlacklist


class MockTokenPayload:
    """Mock TokenPayload for testing."""

    def __init__(self, sub: str, jti: str, exp: int):
        self.sub = sub
        self.jti = jti
        self.exp = exp


class TestTokenBlacklist:
    """Tests for TokenBlacklist class."""

    @pytest.fixture
    def mock_redis(self):
        """Create a mock Redis client."""
        redis = AsyncMock()
        redis.setex = AsyncMock()
        redis.exists = AsyncMock(return_value=0)
        return redis

    @pytest.fixture
    def blacklist(self, mock_redis):
        """Create a TokenBlacklist instance with mock Redis."""
        return TokenBlacklist(redis=mock_redis)

    @pytest.mark.asyncio
    @patch("domains.auth.application.services.token_blacklist.get_blacklist_publisher")
    @patch("domains.auth.application.services.token_blacklist.now_utc")
    @patch("domains.auth.application.services.token_blacklist.compute_ttl_seconds")
    async def test_add_stores_in_redis(
        self,
        mock_compute_ttl,
        mock_now_utc,
        mock_get_publisher,
        blacklist,
        mock_redis,
    ):
        """Test that add() stores token in Redis."""
        mock_compute_ttl.return_value = 3600  # 1 hour
        mock_now_utc.return_value = datetime(2025, 12, 29, 12, 0, 0, tzinfo=timezone.utc)
        mock_get_publisher.return_value = None  # No publisher

        payload = MockTokenPayload(
            sub="user-123",
            jti="token-jti-abc",
            exp=int(datetime(2025, 12, 29, 13, 0, 0, tzinfo=timezone.utc).timestamp()),
        )

        await blacklist.add(payload, reason="logout")

        mock_redis.setex.assert_called_once()
        call_args = mock_redis.setex.call_args

        assert call_args[0][0] == "blacklist:token-jti-abc"
        assert call_args[0][1] == 3600

        stored_data = json.loads(call_args[0][2])
        assert stored_data["user_id"] == "user-123"
        assert stored_data["reason"] == "logout"

    @pytest.mark.asyncio
    @patch("domains.auth.application.services.token_blacklist.get_blacklist_publisher")
    @patch("domains.auth.application.services.token_blacklist.now_utc")
    @patch("domains.auth.application.services.token_blacklist.compute_ttl_seconds")
    async def test_add_skips_expired_token(
        self,
        mock_compute_ttl,
        mock_now_utc,
        mock_get_publisher,
        blacklist,
        mock_redis,
    ):
        """Test that add() skips tokens with expired TTL."""
        mock_compute_ttl.return_value = 0  # Already expired
        mock_now_utc.return_value = datetime(2025, 12, 29, 12, 0, 0, tzinfo=timezone.utc)
        mock_get_publisher.return_value = None

        payload = MockTokenPayload(
            sub="user-123",
            jti="expired-jti",
            exp=int(datetime(2025, 12, 29, 11, 0, 0, tzinfo=timezone.utc).timestamp()),
        )

        await blacklist.add(payload)

        mock_redis.setex.assert_not_called()

    @pytest.mark.asyncio
    @patch("domains.auth.application.services.token_blacklist.get_blacklist_publisher")
    @patch("domains.auth.application.services.token_blacklist.now_utc")
    @patch("domains.auth.application.services.token_blacklist.compute_ttl_seconds")
    async def test_add_publishes_event(
        self,
        mock_compute_ttl,
        mock_now_utc,
        mock_get_publisher,
        blacklist,
        mock_redis,
    ):
        """Test that add() publishes event to RabbitMQ."""
        mock_compute_ttl.return_value = 3600
        mock_now_utc.return_value = datetime(2025, 12, 29, 12, 0, 0, tzinfo=timezone.utc)

        mock_publisher = MagicMock()
        mock_publisher.publish_add.return_value = True
        mock_get_publisher.return_value = mock_publisher

        payload = MockTokenPayload(
            sub="user-123",
            jti="token-jti-xyz",
            exp=int(datetime(2025, 12, 29, 13, 0, 0, tzinfo=timezone.utc).timestamp()),
        )

        await blacklist.add(payload)

        mock_publisher.publish_add.assert_called_once()
        call_args = mock_publisher.publish_add.call_args[0]
        assert call_args[0] == "token-jti-xyz"

    @pytest.mark.asyncio
    @patch("domains.auth.application.services.token_blacklist.get_blacklist_publisher")
    @patch("domains.auth.application.services.token_blacklist.now_utc")
    @patch("domains.auth.application.services.token_blacklist.compute_ttl_seconds")
    async def test_add_handles_publish_failure(
        self,
        mock_compute_ttl,
        mock_now_utc,
        mock_get_publisher,
        blacklist,
        mock_redis,
    ):
        """Test that add() continues even if publish fails."""
        mock_compute_ttl.return_value = 3600
        mock_now_utc.return_value = datetime(2025, 12, 29, 12, 0, 0, tzinfo=timezone.utc)

        mock_publisher = MagicMock()
        mock_publisher.publish_add.return_value = False  # Publish failed
        mock_get_publisher.return_value = mock_publisher

        payload = MockTokenPayload(
            sub="user-123",
            jti="token-jti-fail",
            exp=int(datetime(2025, 12, 29, 13, 0, 0, tzinfo=timezone.utc).timestamp()),
        )

        # Should not raise even if publish fails
        await blacklist.add(payload)

        # Redis should still be called
        mock_redis.setex.assert_called_once()

    @pytest.mark.asyncio
    async def test_contains_returns_true_when_exists(self, blacklist, mock_redis):
        """Test that contains() returns True when token is blacklisted."""
        mock_redis.exists.return_value = 1

        result = await blacklist.contains("existing-jti")

        assert result is True
        mock_redis.exists.assert_called_once_with("blacklist:existing-jti")

    @pytest.mark.asyncio
    async def test_contains_returns_false_when_not_exists(self, blacklist, mock_redis):
        """Test that contains() returns False when token is not blacklisted."""
        mock_redis.exists.return_value = 0

        result = await blacklist.contains("non-existing-jti")

        assert result is False

    def test_key_format(self):
        """Test that _key() generates correct Redis key format."""
        assert TokenBlacklist._key("test-jti") == "blacklist:test-jti"
        assert TokenBlacklist._key("abc-123") == "blacklist:abc-123"
        assert TokenBlacklist._key("") == "blacklist:"


class TestTokenBlacklistIntegration:
    """Integration-style tests for TokenBlacklist."""

    @pytest.mark.asyncio
    @patch("domains.auth.application.services.token_blacklist.get_blacklist_publisher")
    @patch("domains.auth.application.services.token_blacklist.now_utc")
    @patch("domains.auth.application.services.token_blacklist.compute_ttl_seconds")
    async def test_add_then_contains(self, mock_compute_ttl, mock_now_utc, mock_get_publisher):
        """Test add() then contains() flow."""
        mock_compute_ttl.return_value = 3600
        mock_now_utc.return_value = datetime(2025, 12, 29, 12, 0, 0, tzinfo=timezone.utc)
        mock_get_publisher.return_value = None

        # Simulate Redis behavior
        storage = {}

        mock_redis = AsyncMock()

        async def mock_setex(key, ttl, value):
            storage[key] = value

        async def mock_exists(key):
            return 1 if key in storage else 0

        mock_redis.setex = mock_setex
        mock_redis.exists = mock_exists

        blacklist = TokenBlacklist(redis=mock_redis)

        payload = MockTokenPayload(
            sub="user-123",
            jti="integrated-jti",
            exp=int(datetime(2025, 12, 29, 13, 0, 0, tzinfo=timezone.utc).timestamp()),
        )

        # Add to blacklist
        await blacklist.add(payload)

        # Check if contains
        result = await blacklist.contains("integrated-jti")
        assert result is True

        # Check non-existent
        result = await blacklist.contains("non-existent")
        assert result is False
