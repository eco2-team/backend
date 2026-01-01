"""RabbitMQClient 테스트."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.auth_worker.infrastructure.messaging.rabbitmq_client import RabbitMQClient


class TestRabbitMQClient:
    """RabbitMQClient 테스트."""

    @pytest.fixture
    def client(self) -> RabbitMQClient:
        """테스트용 클라이언트 인스턴스."""
        return RabbitMQClient("amqp://localhost:5672")

    def test_init(self, client: RabbitMQClient) -> None:
        """초기화 확인."""
        assert client._amqp_url == "amqp://localhost:5672"
        assert client._connection is None
        assert client._channel is None
        assert client._queue is None
        assert client._shutdown is False

    def test_exchange_and_queue_names(self, client: RabbitMQClient) -> None:
        """Exchange와 Queue 이름 확인."""
        assert client.EXCHANGE_NAME == "blacklist.events"
        assert client.QUEUE_NAME == "auth-worker.blacklist"

    @pytest.mark.asyncio
    async def test_connect(self, client: RabbitMQClient) -> None:
        """연결 테스트."""
        mock_connection = AsyncMock()
        mock_channel = AsyncMock()
        mock_exchange = AsyncMock()
        mock_queue = AsyncMock()

        mock_connection.channel = AsyncMock(return_value=mock_channel)
        mock_channel.declare_exchange = AsyncMock(return_value=mock_exchange)
        mock_channel.declare_queue = AsyncMock(return_value=mock_queue)

        with patch("aio_pika.connect_robust", return_value=mock_connection):
            await client.connect()

            assert client._connection is mock_connection
            assert client._channel is mock_channel
            assert client._queue is mock_queue

            # QoS 설정 확인
            mock_channel.set_qos.assert_awaited_once_with(prefetch_count=10)

            # Exchange 선언 확인
            mock_channel.declare_exchange.assert_awaited_once()

            # Queue 선언 확인
            mock_channel.declare_queue.assert_awaited_once()

            # Queue-Exchange 바인딩 확인
            mock_queue.bind.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_start_consuming_without_connect_raises(
        self,
        client: RabbitMQClient,
    ) -> None:
        """연결 없이 소비 시작시 RuntimeError."""
        callback = AsyncMock()

        with pytest.raises(RuntimeError, match="Not connected"):
            await client.start_consuming(callback)

    @pytest.mark.asyncio
    async def test_start_consuming_calls_queue_consume(
        self,
        client: RabbitMQClient,
    ) -> None:
        """메시지 소비 시작 확인."""
        mock_queue = AsyncMock()
        client._queue = mock_queue
        client._shutdown = True  # 즉시 종료

        callback = AsyncMock()

        await client.start_consuming(callback)

        mock_queue.consume.assert_awaited_once_with(callback, no_ack=False)

    @pytest.mark.asyncio
    async def test_close(self, client: RabbitMQClient) -> None:
        """연결 종료 확인."""
        mock_connection = AsyncMock()
        mock_connection.is_closed = False
        client._connection = mock_connection

        await client.close()

        assert client._shutdown is True
        mock_connection.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_close_already_closed(self, client: RabbitMQClient) -> None:
        """이미 닫힌 연결 종료 시도."""
        mock_connection = AsyncMock()
        mock_connection.is_closed = True
        client._connection = mock_connection

        await client.close()

        assert client._shutdown is True
        mock_connection.close.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_close_no_connection(self, client: RabbitMQClient) -> None:
        """연결 없이 종료."""
        await client.close()

        assert client._shutdown is True
