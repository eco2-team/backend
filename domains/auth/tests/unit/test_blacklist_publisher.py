"""Unit tests for BlacklistEventPublisher."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch


from domains.auth.services.blacklist_publisher import (
    OUTBOX_KEY,
    BlacklistEventPublisher,
    get_blacklist_publisher,
)


class TestGetBlacklistPublisher:
    """Tests for get_blacklist_publisher factory function."""

    def setup_method(self):
        """Reset singleton before each test."""
        import domains.auth.services.blacklist_publisher as module

        module._publisher = None

    @patch("domains.auth.services.blacklist_publisher.get_settings")
    def test_returns_none_when_amqp_not_configured(self, mock_get_settings):
        """Should return None when AMQP URL is not configured."""
        mock_settings = MagicMock()
        mock_settings.amqp_url = None
        mock_get_settings.return_value = mock_settings

        result = get_blacklist_publisher()

        assert result is None

    @patch("domains.auth.services.blacklist_publisher.get_settings")
    def test_returns_publisher_when_amqp_configured(self, mock_get_settings):
        """Should return publisher when AMQP URL is configured."""
        mock_settings = MagicMock()
        mock_settings.amqp_url = "amqp://localhost:5672/"
        mock_get_settings.return_value = mock_settings

        result = get_blacklist_publisher()

        assert result is not None
        assert isinstance(result, BlacklistEventPublisher)

    @patch("domains.auth.services.blacklist_publisher.get_settings")
    def test_returns_singleton(self, mock_get_settings):
        """Should return same instance on subsequent calls."""
        mock_settings = MagicMock()
        mock_settings.amqp_url = "amqp://localhost:5672/"
        mock_get_settings.return_value = mock_settings

        publisher1 = get_blacklist_publisher()
        publisher2 = get_blacklist_publisher()

        assert publisher1 is publisher2


class TestBlacklistEventPublisher:
    """Tests for BlacklistEventPublisher class."""

    def test_init(self):
        """Should initialize with AMQP URL."""
        amqp_url = "amqp://localhost:5672/"
        publisher = BlacklistEventPublisher(amqp_url)

        assert publisher.amqp_url == amqp_url
        assert publisher._connection is None
        assert publisher._channel is None

    @patch("pika.BlockingConnection")
    @patch("pika.URLParameters")
    def test_ensure_connection_creates_connection(self, mock_url_params, mock_blocking):
        """Should create new connection when none exists."""
        mock_connection = MagicMock()
        mock_channel = MagicMock()
        mock_connection.channel.return_value = mock_channel
        mock_blocking.return_value = mock_connection

        publisher = BlacklistEventPublisher("amqp://localhost:5672/")
        publisher._ensure_connection()

        mock_url_params.assert_called_once()
        mock_blocking.assert_called_once()
        mock_channel.exchange_declare.assert_called_once_with(
            exchange="blacklist.events",
            exchange_type="fanout",
            durable=True,
        )

    def test_ensure_connection_reuses_existing(self):
        """Should reuse existing connection if not closed."""
        mock_connection = MagicMock()
        mock_connection.is_closed = False

        publisher = BlacklistEventPublisher("amqp://localhost:5672/")
        publisher._connection = mock_connection

        # Should not raise or create new connection
        publisher._ensure_connection()

        # Connection should still be the same
        assert publisher._connection is mock_connection

    @patch("pika.BlockingConnection")
    @patch("pika.URLParameters")
    @patch("pika.BasicProperties")
    def test_publish_add_success(self, mock_props, mock_url_params, mock_blocking):
        """Should publish event and return True on success."""
        mock_connection = MagicMock()
        mock_connection.is_closed = False
        mock_channel = MagicMock()
        mock_connection.channel.return_value = mock_channel
        mock_blocking.return_value = mock_connection

        publisher = BlacklistEventPublisher("amqp://localhost:5672/")
        expires_at = datetime(2025, 12, 31, 23, 59, 59, tzinfo=timezone.utc)

        result = publisher.publish_add("test-jti-12345678", expires_at)

        assert result is True
        mock_channel.basic_publish.assert_called_once()

        # Verify event structure
        call_args = mock_channel.basic_publish.call_args
        body = json.loads(call_args.kwargs["body"])
        assert body["type"] == "add"
        assert body["jti"] == "test-jti-12345678"
        assert "expires_at" in body
        assert "timestamp" in body

    @patch("pika.BlockingConnection")
    @patch("pika.URLParameters")
    @patch("redis.from_url")
    @patch.dict("os.environ", {"AUTH_REDIS_URL": "redis://localhost:6379/0"})
    def test_publish_add_failure_queues_to_outbox(
        self, mock_redis_from_url, mock_url_params, mock_blocking
    ):
        """Should queue to outbox when MQ publish fails."""
        mock_blocking.side_effect = Exception("Connection failed")
        mock_redis_client = MagicMock()
        mock_redis_from_url.return_value = mock_redis_client

        publisher = BlacklistEventPublisher("amqp://localhost:5672/")
        expires_at = datetime(2025, 12, 31, 23, 59, 59, tzinfo=timezone.utc)

        result = publisher.publish_add("test-jti-12345678", expires_at)

        assert result is False
        mock_redis_client.lpush.assert_called_once()

        # Verify event structure in outbox
        call_args = mock_redis_client.lpush.call_args
        assert call_args[0][0] == OUTBOX_KEY
        event = json.loads(call_args[0][1])
        assert event["type"] == "add"
        assert event["jti"] == "test-jti-12345678"


class TestQueueToOutbox:
    """Tests for _queue_to_outbox method."""

    @patch.dict("os.environ", {}, clear=True)
    def test_returns_false_when_redis_url_not_set(self):
        """Should return False when AUTH_REDIS_URL is not set."""
        # Clear AUTH_REDIS_URL
        import os

        if "AUTH_REDIS_URL" in os.environ:
            del os.environ["AUTH_REDIS_URL"]

        publisher = BlacklistEventPublisher("amqp://localhost:5672/")
        event = {"type": "add", "jti": "test-jti"}

        result = publisher._queue_to_outbox(event)

        assert result is False

    @patch("redis.from_url")
    @patch.dict("os.environ", {"AUTH_REDIS_URL": "redis://localhost:6379/0"})
    def test_queues_event_to_redis(self, mock_redis_from_url):
        """Should LPUSH event to Redis outbox."""
        mock_redis_client = MagicMock()
        mock_redis_from_url.return_value = mock_redis_client

        publisher = BlacklistEventPublisher("amqp://localhost:5672/")
        event = {"type": "add", "jti": "test-jti-12345678"}

        result = publisher._queue_to_outbox(event)

        assert result is True
        mock_redis_from_url.assert_called_once_with("redis://localhost:6379/0")
        mock_redis_client.lpush.assert_called_once()

    @patch("redis.from_url")
    @patch.dict("os.environ", {"AUTH_REDIS_URL": "redis://localhost:6379/0"})
    def test_returns_false_on_redis_error(self, mock_redis_from_url):
        """Should return False when Redis operation fails."""
        mock_redis_from_url.side_effect = Exception("Redis error")

        publisher = BlacklistEventPublisher("amqp://localhost:5672/")
        event = {"type": "add", "jti": "test-jti"}

        result = publisher._queue_to_outbox(event)

        assert result is False


class TestClose:
    """Tests for close method."""

    def test_close_when_no_connection(self):
        """Should handle close when no connection exists."""
        publisher = BlacklistEventPublisher("amqp://localhost:5672/")

        # Should not raise
        publisher.close()

    def test_close_when_connection_already_closed(self):
        """Should handle close when connection already closed."""
        mock_connection = MagicMock()
        mock_connection.is_closed = True

        publisher = BlacklistEventPublisher("amqp://localhost:5672/")
        publisher._connection = mock_connection

        publisher.close()

        mock_connection.close.assert_not_called()

    def test_close_closes_connection(self):
        """Should close active connection."""
        mock_connection = MagicMock()
        mock_connection.is_closed = False

        publisher = BlacklistEventPublisher("amqp://localhost:5672/")
        publisher._connection = mock_connection

        publisher.close()

        mock_connection.close.assert_called_once()
