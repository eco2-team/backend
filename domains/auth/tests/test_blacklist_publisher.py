"""Tests for blacklist_publisher module."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch


from domains.auth.application.services.blacklist_publisher import (
    BlacklistEventPublisher,
    get_blacklist_publisher,
)


class TestBlacklistEventPublisher:
    """Tests for BlacklistEventPublisher class."""

    def test_init(self):
        """Test publisher initialization."""
        publisher = BlacklistEventPublisher("amqp://localhost:5672/")

        assert publisher.amqp_url == "amqp://localhost:5672/"
        assert publisher._connection is None
        assert publisher._channel is None

    @patch("pika.BlockingConnection")
    def test_ensure_connection_success(self, mock_blocking_connection):
        """Test successful connection establishment."""
        mock_connection = MagicMock()
        mock_channel = MagicMock()
        mock_connection.is_closed = False
        mock_connection.channel.return_value = mock_channel
        mock_blocking_connection.return_value = mock_connection

        publisher = BlacklistEventPublisher("amqp://localhost:5672/")
        publisher._ensure_connection()

        mock_blocking_connection.assert_called_once()
        mock_connection.channel.assert_called_once()
        mock_channel.exchange_declare.assert_called_once_with(
            exchange="blacklist.events",
            exchange_type="fanout",
            durable=True,
        )

    @patch("pika.BlockingConnection")
    def test_publish_add_success(self, mock_blocking_connection):
        """Test successful event publishing."""
        mock_connection = MagicMock()
        mock_channel = MagicMock()
        mock_connection.is_closed = False
        mock_connection.channel.return_value = mock_channel
        mock_blocking_connection.return_value = mock_connection

        publisher = BlacklistEventPublisher("amqp://localhost:5672/")

        jti = "test-jti-123"
        expires_at = datetime(2025, 12, 30, 12, 0, 0, tzinfo=timezone.utc)

        result = publisher.publish_add(jti, expires_at)

        assert result is True
        mock_channel.basic_publish.assert_called_once()

        call_args = mock_channel.basic_publish.call_args
        assert call_args.kwargs["exchange"] == "blacklist.events"
        assert call_args.kwargs["routing_key"] == ""

        body = json.loads(call_args.kwargs["body"])
        assert body["type"] == "add"
        assert body["jti"] == jti
        assert body["expires_at"] == "2025-12-30T12:00:00+00:00"

    @patch("pika.BlockingConnection")
    def test_publish_add_connection_failure(self, mock_blocking_connection):
        """Test publishing when connection fails."""
        mock_blocking_connection.side_effect = Exception("Connection refused")

        publisher = BlacklistEventPublisher("amqp://localhost:5672/")

        jti = "test-jti-123"
        expires_at = datetime(2025, 12, 30, 12, 0, 0, tzinfo=timezone.utc)

        result = publisher.publish_add(jti, expires_at)

        assert result is False
        assert publisher._connection is None
        assert publisher._channel is None

    @patch("pika.BlockingConnection")
    def test_publish_add_publish_failure(self, mock_blocking_connection):
        """Test publishing when basic_publish fails."""
        mock_connection = MagicMock()
        mock_channel = MagicMock()
        mock_connection.is_closed = False
        mock_connection.channel.return_value = mock_channel
        mock_channel.basic_publish.side_effect = Exception("Publish failed")
        mock_blocking_connection.return_value = mock_connection

        publisher = BlacklistEventPublisher("amqp://localhost:5672/")

        jti = "test-jti-123"
        expires_at = datetime(2025, 12, 30, 12, 0, 0, tzinfo=timezone.utc)

        result = publisher.publish_add(jti, expires_at)

        assert result is False
        # Connection should be reset on failure
        assert publisher._connection is None
        assert publisher._channel is None

    @patch("pika.BlockingConnection")
    def test_close(self, mock_blocking_connection):
        """Test closing the connection."""
        mock_connection = MagicMock()
        mock_channel = MagicMock()
        mock_connection.is_closed = False
        mock_connection.channel.return_value = mock_channel
        mock_blocking_connection.return_value = mock_connection

        publisher = BlacklistEventPublisher("amqp://localhost:5672/")
        publisher._ensure_connection()

        publisher.close()

        mock_connection.close.assert_called_once()

    def test_close_without_connection(self):
        """Test closing when no connection exists."""
        publisher = BlacklistEventPublisher("amqp://localhost:5672/")

        # Should not raise
        publisher.close()

    @patch("pika.BlockingConnection")
    def test_reconnect_on_closed_connection(self, mock_blocking_connection):
        """Test reconnection when connection is closed."""
        mock_connection = MagicMock()
        mock_channel = MagicMock()
        mock_connection.channel.return_value = mock_channel
        mock_blocking_connection.return_value = mock_connection

        publisher = BlacklistEventPublisher("amqp://localhost:5672/")

        # First connection
        mock_connection.is_closed = False
        publisher._ensure_connection()
        assert mock_blocking_connection.call_count == 1

        # Mark connection as closed
        mock_connection.is_closed = True

        # Should reconnect
        publisher._ensure_connection()
        assert mock_blocking_connection.call_count == 2


class TestGetBlacklistPublisher:
    """Tests for get_blacklist_publisher function."""

    def setup_method(self):
        """Reset global publisher before each test."""
        import domains.auth.application.services.blacklist_publisher as module

        module._publisher = None

    def teardown_method(self):
        """Reset global publisher after each test."""
        import domains.auth.application.services.blacklist_publisher as module

        module._publisher = None

    @patch("domains.auth.application.services.blacklist_publisher.get_settings")
    def test_returns_none_when_no_amqp_url(self, mock_get_settings):
        """Test that None is returned when AMQP_URL is not configured."""
        mock_settings = MagicMock()
        mock_settings.amqp_url = None
        mock_get_settings.return_value = mock_settings

        result = get_blacklist_publisher()

        assert result is None

    @patch("domains.auth.application.services.blacklist_publisher.get_settings")
    @patch("pika.BlockingConnection")
    def test_returns_singleton(self, mock_blocking_connection, mock_get_settings):
        """Test that the same instance is returned on subsequent calls."""
        mock_settings = MagicMock()
        mock_settings.amqp_url = "amqp://localhost:5672/"
        mock_get_settings.return_value = mock_settings

        publisher1 = get_blacklist_publisher()
        publisher2 = get_blacklist_publisher()

        assert publisher1 is publisher2
        # First call creates, second call returns cached
        assert publisher1 is not None

    @patch("domains.auth.application.services.blacklist_publisher.BlacklistEventPublisher")
    @patch("domains.auth.application.services.blacklist_publisher.get_settings")
    def test_returns_none_on_init_failure(self, mock_get_settings, mock_publisher_class):
        """Test that None is returned when publisher initialization fails."""
        mock_settings = MagicMock()
        mock_settings.amqp_url = "amqp://localhost:5672/"
        mock_get_settings.return_value = mock_settings

        # Make publisher initialization fail
        mock_publisher_class.side_effect = Exception("Connection failed")

        result = get_blacklist_publisher()

        # Should return None on failure
        assert result is None


class TestEventSerialization:
    """Tests for event JSON serialization."""

    def test_event_structure(self):
        """Test that event has correct structure."""
        jti = "test-jti-abc123"
        expires_at = datetime(2025, 12, 30, 12, 0, 0, tzinfo=timezone.utc)

        event = {
            "type": "add",
            "jti": jti,
            "expires_at": expires_at.isoformat(),
        }

        serialized = json.dumps(event)
        deserialized = json.loads(serialized)

        assert deserialized["type"] == "add"
        assert deserialized["jti"] == jti
        assert deserialized["expires_at"] == "2025-12-30T12:00:00+00:00"

    def test_event_with_naive_datetime(self):
        """Test event with naive datetime (no timezone)."""
        jti = "test-jti-naive"
        expires_at = datetime(2025, 12, 30, 12, 0, 0)  # Naive

        event = {
            "type": "add",
            "jti": jti,
            "expires_at": expires_at.isoformat(),
        }

        serialized = json.dumps(event)
        deserialized = json.loads(serialized)

        assert deserialized["expires_at"] == "2025-12-30T12:00:00"
