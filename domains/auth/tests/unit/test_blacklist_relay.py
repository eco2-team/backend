"""Unit tests for BlacklistRelay worker."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pika
import pika.exceptions
import pytest

from domains.auth.workers.blacklist_relay import (
    BATCH_SIZE,
    DLQ_KEY,
    EXCHANGE_NAME,
    OUTBOX_KEY,
    BlacklistRelay,
)


class TestBlacklistRelayInit:
    """Tests for BlacklistRelay initialization."""

    def test_init_defaults(self):
        """Should initialize with default values."""
        relay = BlacklistRelay()

        assert relay._redis is None
        assert relay._mq_connection is None
        assert relay._mq_channel is None
        assert relay._shutdown is False
        assert relay._processed_total == 0
        assert relay._failed_total == 0


class TestConnectMq:
    """Tests for _connect_mq method."""

    @patch("domains.auth.workers.blacklist_relay.pika")
    def test_connect_mq_success(self, mock_pika):
        """Should establish RabbitMQ connection."""
        mock_connection = MagicMock()
        mock_channel = MagicMock()
        mock_connection.channel.return_value = mock_channel
        mock_pika.BlockingConnection.return_value = mock_connection

        relay = BlacklistRelay()
        relay._connect_mq()

        mock_pika.URLParameters.assert_called_once()
        mock_pika.BlockingConnection.assert_called_once()
        mock_channel.exchange_declare.assert_called_once_with(
            exchange=EXCHANGE_NAME,
            exchange_type="fanout",
            durable=True,
        )

    @patch("domains.auth.workers.blacklist_relay.pika")
    def test_connect_mq_failure_raises(self, mock_pika):
        """Should raise exception on connection failure."""
        mock_pika.BlockingConnection.side_effect = Exception("Connection failed")

        relay = BlacklistRelay()

        with pytest.raises(Exception, match="Connection failed"):
            relay._connect_mq()


class TestHandleShutdown:
    """Tests for _handle_shutdown method."""

    def test_sets_shutdown_flag(self):
        """Should set shutdown flag to True."""
        relay = BlacklistRelay()

        relay._handle_shutdown()

        assert relay._shutdown is True


class TestPublishToMq:
    """Tests for _publish_to_mq method."""

    def test_publishes_event(self):
        """Should publish event to RabbitMQ."""
        relay = BlacklistRelay()
        relay._mq_channel = MagicMock()

        event = {"type": "add", "jti": "test-jti-12345678"}
        relay._publish_to_mq(event)

        relay._mq_channel.basic_publish.assert_called_once()
        call_args = relay._mq_channel.basic_publish.call_args

        assert call_args.kwargs["exchange"] == EXCHANGE_NAME
        assert call_args.kwargs["routing_key"] == ""

        body = json.loads(call_args.kwargs["body"].decode("utf-8"))
        assert body["type"] == "add"
        assert body["jti"] == "test-jti-12345678"


class TestReconnectMq:
    """Tests for _reconnect_mq method."""

    @patch("domains.auth.workers.blacklist_relay.pika")
    def test_closes_existing_connection(self, mock_pika):
        """Should close existing connection before reconnecting."""
        mock_old_connection = MagicMock()
        mock_old_connection.is_closed = False
        mock_new_connection = MagicMock()
        mock_pika.BlockingConnection.return_value = mock_new_connection

        relay = BlacklistRelay()
        relay._mq_connection = mock_old_connection

        relay._reconnect_mq()

        mock_old_connection.close.assert_called_once()
        mock_pika.BlockingConnection.assert_called_once()

    @patch("domains.auth.workers.blacklist_relay.pika")
    def test_handles_close_error(self, mock_pika):
        """Should handle error when closing connection."""
        mock_old_connection = MagicMock()
        mock_old_connection.is_closed = False
        mock_old_connection.close.side_effect = Exception("Close failed")
        mock_new_connection = MagicMock()
        mock_pika.BlockingConnection.return_value = mock_new_connection

        relay = BlacklistRelay()
        relay._mq_connection = mock_old_connection

        # Should not raise
        relay._reconnect_mq()

        mock_pika.BlockingConnection.assert_called_once()


class TestProcessBatch:
    """Tests for _process_batch method."""

    @pytest.mark.asyncio
    async def test_returns_zero_when_outbox_empty(self):
        """Should return 0 when outbox is empty."""
        relay = BlacklistRelay()
        relay._redis = AsyncMock()
        relay._redis.rpop.return_value = None

        result = await relay._process_batch()

        assert result == 0

    @pytest.mark.asyncio
    async def test_processes_valid_event(self):
        """Should process valid event from outbox."""
        relay = BlacklistRelay()
        relay._redis = AsyncMock()
        relay._mq_channel = MagicMock()

        event = {"type": "add", "jti": "test-jti-12345678"}
        relay._redis.rpop.side_effect = [json.dumps(event), None]

        result = await relay._process_batch()

        assert result == 1
        assert relay._processed_total == 1
        relay._mq_channel.basic_publish.assert_called_once()

    @pytest.mark.asyncio
    async def test_processes_multiple_events(self):
        """Should process multiple events in a batch."""
        relay = BlacklistRelay()
        relay._redis = AsyncMock()
        relay._mq_channel = MagicMock()

        events = [{"type": "add", "jti": f"test-jti-{i}"} for i in range(3)]
        relay._redis.rpop.side_effect = [json.dumps(e) for e in events] + [None]

        result = await relay._process_batch()

        assert result == 3
        assert relay._processed_total == 3
        assert relay._mq_channel.basic_publish.call_count == 3

    @pytest.mark.asyncio
    async def test_invalid_json_goes_to_dlq(self):
        """Should move invalid JSON to DLQ."""
        relay = BlacklistRelay()
        relay._redis = AsyncMock()
        relay._mq_channel = MagicMock()

        relay._redis.rpop.side_effect = ["invalid json", None]

        result = await relay._process_batch()

        assert result == 0
        assert relay._failed_total == 1
        relay._redis.lpush.assert_called_once()
        assert relay._redis.lpush.call_args[0][0] == DLQ_KEY

    @pytest.mark.asyncio
    async def test_mq_error_requeues_event(self):
        """Should requeue event on MQ publish failure."""
        relay = BlacklistRelay()
        relay._redis = AsyncMock()
        relay._mq_channel = MagicMock()
        relay._mq_channel.basic_publish.side_effect = pika.exceptions.AMQPError("MQ error")
        relay._mq_connection = MagicMock()
        relay._mq_connection.is_closed = True

        event = {"type": "add", "jti": "test-jti-12345678"}
        relay._redis.rpop.side_effect = [json.dumps(event)]

        result = await relay._process_batch()

        assert result == 0
        relay._redis.lpush.assert_called_once()
        assert relay._redis.lpush.call_args[0][0] == OUTBOX_KEY

    @pytest.mark.asyncio
    async def test_respects_batch_size(self):
        """Should not process more than BATCH_SIZE events."""
        relay = BlacklistRelay()
        relay._redis = AsyncMock()
        relay._mq_channel = MagicMock()

        # Return more events than BATCH_SIZE
        events = [json.dumps({"type": "add", "jti": f"jti-{i}"}) for i in range(BATCH_SIZE + 5)]
        relay._redis.rpop.side_effect = events

        result = await relay._process_batch()

        assert result == BATCH_SIZE
        assert relay._redis.rpop.call_count == BATCH_SIZE


class TestCleanup:
    """Tests for _cleanup method."""

    @pytest.mark.asyncio
    async def test_closes_redis(self):
        """Should close Redis connection."""
        relay = BlacklistRelay()
        relay._redis = AsyncMock()
        relay._mq_connection = None

        await relay._cleanup()

        relay._redis.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_closes_mq(self):
        """Should close MQ connection."""
        relay = BlacklistRelay()
        relay._redis = None
        relay._mq_connection = MagicMock()
        relay._mq_connection.is_closed = False

        await relay._cleanup()

        relay._mq_connection.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_handles_already_closed_mq(self):
        """Should handle already closed MQ connection."""
        relay = BlacklistRelay()
        relay._redis = None
        relay._mq_connection = MagicMock()
        relay._mq_connection.is_closed = True

        await relay._cleanup()

        relay._mq_connection.close.assert_not_called()


class TestRun:
    """Tests for _run method."""

    @pytest.mark.asyncio
    async def test_stops_on_shutdown(self):
        """Should stop loop when shutdown flag is set."""
        relay = BlacklistRelay()
        relay._redis = AsyncMock()
        relay._shutdown = True

        await relay._run()

        # Should call cleanup
        relay._redis.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_continues_on_exception(self):
        """Should continue loop on general exception."""
        relay = BlacklistRelay()
        relay._redis = AsyncMock()
        relay._redis.rpop.side_effect = [Exception("Test error"), None]

        # Set shutdown after first iteration
        call_count = 0

        async def mock_sleep(duration):
            nonlocal call_count
            call_count += 1
            if call_count >= 1:
                relay._shutdown = True

        with patch("asyncio.sleep", mock_sleep):
            await relay._run()

        # Should have slept (error recovery) and then stopped
        assert relay._shutdown is True

    @pytest.mark.asyncio
    async def test_handles_amqp_connection_error(self):
        """Should reconnect on AMQP connection error."""
        relay = BlacklistRelay()
        relay._redis = AsyncMock()
        relay._mq_connection = MagicMock()
        relay._mq_connection.is_closed = True

        # First call raises AMQP error, then shutdown
        call_count = 0

        async def mock_process_batch():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise pika.exceptions.AMQPConnectionError("Connection lost")
            return 0

        relay._process_batch = mock_process_batch

        async def mock_sleep(duration):
            relay._shutdown = True

        with patch("asyncio.sleep", mock_sleep):
            with patch.object(relay, "_reconnect_mq"):
                await relay._run()

        assert relay._shutdown is True


class TestStart:
    """Tests for start method."""

    @pytest.mark.asyncio
    @patch("domains.auth.workers.blacklist_relay.Redis")
    @patch("domains.auth.workers.blacklist_relay.pika")
    async def test_start_connects_to_redis_and_mq(self, mock_pika, mock_redis_class):
        """Should connect to Redis and RabbitMQ on start."""
        # Setup mocks
        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock()
        mock_redis.llen = AsyncMock(return_value=0)
        mock_redis.close = AsyncMock()
        mock_redis_class.from_url.return_value = mock_redis

        mock_connection = MagicMock()
        mock_channel = MagicMock()
        mock_connection.channel.return_value = mock_channel
        mock_connection.is_closed = False
        mock_pika.BlockingConnection.return_value = mock_connection

        relay = BlacklistRelay()
        relay._shutdown = True  # Stop immediately after setup

        # Mock signal handlers to avoid actual signal registration
        with patch("asyncio.get_event_loop") as mock_loop:
            mock_event_loop = MagicMock()
            mock_loop.return_value = mock_event_loop

            await relay.start()

        mock_redis.ping.assert_called_once()
        mock_pika.BlockingConnection.assert_called_once()

    @pytest.mark.asyncio
    @patch("domains.auth.workers.blacklist_relay.Redis")
    async def test_start_fails_on_redis_error(self, mock_redis_class):
        """Should raise on Redis connection failure."""
        mock_redis = AsyncMock()
        mock_redis.ping.side_effect = Exception("Redis unavailable")
        mock_redis_class.from_url.return_value = mock_redis

        relay = BlacklistRelay()

        with pytest.raises(Exception, match="Redis unavailable"):
            await relay.start()


class TestProcessBatchEdgeCases:
    """Additional edge case tests for _process_batch."""

    @pytest.mark.asyncio
    async def test_unexpected_exception_goes_to_dlq(self):
        """Should move event to DLQ on unexpected exception during processing."""
        relay = BlacklistRelay()
        relay._redis = AsyncMock()
        relay._mq_channel = MagicMock()

        # Valid JSON but processing fails
        event = {"type": "add", "jti": "test-jti-12345678"}
        relay._redis.rpop.side_effect = [json.dumps(event), None]
        relay._mq_channel.basic_publish.side_effect = RuntimeError("Unexpected error")

        # This should catch the exception and move to DLQ
        with patch.object(relay, "_reconnect_mq"):
            await relay._process_batch()

        # RuntimeError is not AMQPError, so it goes to DLQ
        assert relay._failed_total == 1
        assert relay._redis.lpush.call_args[0][0] == DLQ_KEY
