"""Tests for RabbitMQEventPublisher."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from apps.auth_relay.infrastructure.messaging.rabbitmq_publisher import (
    RabbitMQEventPublisher,
)


class TestRabbitMQEventPublisher:
    """RabbitMQEventPublisher tests."""

    @pytest.fixture
    def publisher(self) -> RabbitMQEventPublisher:
        """Create publisher."""
        return RabbitMQEventPublisher("amqp://localhost")

    @pytest.mark.asyncio
    async def test_connect_establishes_connection(
        self,
        publisher: RabbitMQEventPublisher,
    ) -> None:
        """connect() should establish connection and declare exchange."""
        mock_connection = AsyncMock()
        mock_channel = AsyncMock()
        mock_exchange = AsyncMock()

        mock_connection.is_closed = False
        mock_connection.channel.return_value = mock_channel
        mock_channel.declare_exchange.return_value = mock_exchange

        with patch("aio_pika.connect_robust", return_value=mock_connection):
            await publisher.connect()

        mock_channel.declare_exchange.assert_called_once()
        assert publisher._exchange is mock_exchange

    @pytest.mark.asyncio
    async def test_connect_skips_if_already_connected(
        self,
        publisher: RabbitMQEventPublisher,
    ) -> None:
        """connect() should skip if already connected."""
        mock_connection = AsyncMock()
        mock_connection.is_closed = False
        publisher._connection = mock_connection

        with patch("aio_pika.connect_robust") as mock_connect:
            await publisher.connect()

        mock_connect.assert_not_called()

    @pytest.mark.asyncio
    async def test_close_closes_connection(
        self,
        publisher: RabbitMQEventPublisher,
    ) -> None:
        """close() should close connection."""
        mock_connection = AsyncMock()
        mock_connection.is_closed = False
        publisher._connection = mock_connection

        await publisher.close()

        mock_connection.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_handles_none_connection(
        self,
        publisher: RabbitMQEventPublisher,
    ) -> None:
        """close() should handle None connection gracefully."""
        await publisher.close()  # Should not raise

    @pytest.mark.asyncio
    async def test_close_handles_closed_connection(
        self,
        publisher: RabbitMQEventPublisher,
    ) -> None:
        """close() should skip already closed connection."""
        mock_connection = AsyncMock()
        mock_connection.is_closed = True
        publisher._connection = mock_connection

        await publisher.close()

        mock_connection.close.assert_not_called()

    @pytest.mark.asyncio
    async def test_publish_sends_message(
        self,
        publisher: RabbitMQEventPublisher,
    ) -> None:
        """publish() should send message to exchange."""
        mock_exchange = AsyncMock()
        publisher._exchange = mock_exchange

        await publisher.publish('{"jti": "abc"}')

        mock_exchange.publish.assert_called_once()
        call_args = mock_exchange.publish.call_args
        message = call_args[0][0]
        assert message.body == b'{"jti": "abc"}'

    @pytest.mark.asyncio
    async def test_publish_connects_if_not_connected(
        self,
        publisher: RabbitMQEventPublisher,
    ) -> None:
        """publish() should connect if exchange is None."""
        mock_connection = AsyncMock()
        mock_channel = AsyncMock()
        mock_exchange = AsyncMock()

        mock_connection.channel.return_value = mock_channel
        mock_channel.declare_exchange.return_value = mock_exchange

        with patch("aio_pika.connect_robust", return_value=mock_connection):
            await publisher.publish('{"jti": "abc"}')

        mock_exchange.publish.assert_called_once()

    def test_exchange_name_constant(self) -> None:
        """Should have correct exchange name."""
        assert RabbitMQEventPublisher.EXCHANGE_NAME == "blacklist.events"
