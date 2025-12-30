"""Unit tests for BlacklistEventPublisher."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from domains.auth.application.services.blacklist_publisher import (
    OUTBOX_KEY,
    BlacklistEventPublisher,
    get_blacklist_publisher,
)


class TestGetBlacklistPublisher:
    """Tests for get_blacklist_publisher factory function."""

    def setup_method(self):
        """Reset singleton before each test."""
        import domains.auth.application.services.blacklist_publisher as module

        module._publisher = None

    @patch("domains.auth.application.services.blacklist_publisher.get_settings")
    def test_returns_none_when_amqp_not_configured(self, mock_get_settings):
        """Should return None when AMQP URL is not configured."""
        mock_settings = MagicMock()
        mock_settings.amqp_url = None
        mock_get_settings.return_value = mock_settings

        result = get_blacklist_publisher()

        assert result is None

    @patch("domains.auth.application.services.blacklist_publisher._create_outbox_repository")
    @patch("domains.auth.application.services.blacklist_publisher.get_settings")
    def test_returns_publisher_when_amqp_configured(self, mock_get_settings, mock_create_outbox):
        """Should return publisher when AMQP URL is configured."""
        mock_settings = MagicMock()
        mock_settings.amqp_url = "amqp://localhost:5672/"
        mock_get_settings.return_value = mock_settings
        mock_create_outbox.return_value = MagicMock()

        result = get_blacklist_publisher()

        assert result is not None
        assert isinstance(result, BlacklistEventPublisher)

    @patch("domains.auth.application.services.blacklist_publisher._create_outbox_repository")
    @patch("domains.auth.application.services.blacklist_publisher.get_settings")
    def test_returns_singleton(self, mock_get_settings, mock_create_outbox):
        """Should return same instance on subsequent calls."""
        mock_settings = MagicMock()
        mock_settings.amqp_url = "amqp://localhost:5672/"
        mock_get_settings.return_value = mock_settings
        mock_create_outbox.return_value = MagicMock()

        publisher1 = get_blacklist_publisher()
        publisher2 = get_blacklist_publisher()

        assert publisher1 is publisher2


class TestBlacklistEventPublisher:
    """Tests for BlacklistEventPublisher class."""

    def test_init(self):
        """Should initialize with AMQP URL and optional outbox."""
        amqp_url = "amqp://localhost:5672/"
        mock_outbox = MagicMock()
        publisher = BlacklistEventPublisher(amqp_url, outbox=mock_outbox)

        assert publisher.amqp_url == amqp_url
        assert publisher._outbox is mock_outbox
        assert publisher._connection is None
        assert publisher._channel is None

    def test_init_without_outbox(self):
        """Should initialize without outbox (outbox is optional)."""
        amqp_url = "amqp://localhost:5672/"
        publisher = BlacklistEventPublisher(amqp_url)

        assert publisher.amqp_url == amqp_url
        assert publisher._outbox is None

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
    def test_publish_add_failure_queues_to_outbox(self, mock_url_params, mock_blocking):
        """Should queue to outbox when MQ publish fails."""
        mock_blocking.side_effect = Exception("Connection failed")
        mock_outbox = MagicMock()
        mock_outbox.push.return_value = True

        publisher = BlacklistEventPublisher("amqp://localhost:5672/", outbox=mock_outbox)
        expires_at = datetime(2025, 12, 31, 23, 59, 59, tzinfo=timezone.utc)

        result = publisher.publish_add("test-jti-12345678", expires_at)

        assert result is False
        mock_outbox.push.assert_called_once()

        # Verify event structure in outbox
        call_args = mock_outbox.push.call_args
        assert call_args[0][0] == OUTBOX_KEY
        event = json.loads(call_args[0][1])
        assert event["type"] == "add"
        assert event["jti"] == "test-jti-12345678"


class TestQueueToOutbox:
    """Tests for _queue_to_outbox method."""

    def test_returns_false_when_outbox_not_configured(self):
        """Should return False when outbox is not configured."""
        publisher = BlacklistEventPublisher("amqp://localhost:5672/")  # No outbox
        event = {"type": "add", "jti": "test-jti"}

        result = publisher._queue_to_outbox(event)

        assert result is False

    def test_queues_event_to_outbox(self):
        """Should push event to outbox repository."""
        mock_outbox = MagicMock()
        mock_outbox.push.return_value = True

        publisher = BlacklistEventPublisher("amqp://localhost:5672/", outbox=mock_outbox)
        event = {"type": "add", "jti": "test-jti-12345678"}

        result = publisher._queue_to_outbox(event)

        assert result is True
        mock_outbox.push.assert_called_once_with(OUTBOX_KEY, json.dumps(event))

    def test_returns_false_on_outbox_error(self):
        """Should return False when outbox operation fails."""
        mock_outbox = MagicMock()
        mock_outbox.push.side_effect = Exception("Outbox error")

        publisher = BlacklistEventPublisher("amqp://localhost:5672/", outbox=mock_outbox)
        event = {"type": "add", "jti": "test-jti"}

        result = publisher._queue_to_outbox(event)

        assert result is False

    def test_returns_false_when_outbox_push_returns_false(self):
        """Should return False when outbox.push() returns False."""
        mock_outbox = MagicMock()
        mock_outbox.push.return_value = False

        publisher = BlacklistEventPublisher("amqp://localhost:5672/", outbox=mock_outbox)
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
