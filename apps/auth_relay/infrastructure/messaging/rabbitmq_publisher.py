"""RabbitMQ Event Publisher.

EventPublisher 포트의 RabbitMQ 구현체입니다.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import aio_pika
from aio_pika import DeliveryMode, ExchangeType, Message

if TYPE_CHECKING:
    from aio_pika.abc import AbstractChannel, AbstractConnection, AbstractExchange

logger = logging.getLogger(__name__)


class RabbitMQEventPublisher:
    """RabbitMQ 기반 이벤트 발행자.

    EventPublisher 인터페이스 구현체입니다.
    Fanout Exchange로 이벤트를 발행합니다.
    """

    EXCHANGE_NAME = "blacklist.events"

    def __init__(self, amqp_url: str) -> None:
        """Initialize.

        Args:
            amqp_url: RabbitMQ 연결 URL
        """
        self._amqp_url = amqp_url
        self._connection: AbstractConnection | None = None
        self._channel: AbstractChannel | None = None
        self._exchange: AbstractExchange | None = None

    async def connect(self) -> None:
        """RabbitMQ 연결."""
        if self._connection and not self._connection.is_closed:
            return

        self._connection = await aio_pika.connect_robust(self._amqp_url)
        self._channel = await self._connection.channel()

        # Fanout Exchange 선언 (durable)
        self._exchange = await self._channel.declare_exchange(
            self.EXCHANGE_NAME,
            ExchangeType.FANOUT,
            durable=True,
        )
        logger.info(
            "RabbitMQ connected for relay",
            extra={"exchange": self.EXCHANGE_NAME},
        )

    async def close(self) -> None:
        """연결 종료."""
        if self._connection and not self._connection.is_closed:
            await self._connection.close()
            logger.debug("RabbitMQ connection closed")

    async def publish(self, event_json: str) -> None:
        """이벤트 발행.

        Args:
            event_json: 이벤트 JSON 문자열

        Raises:
            ConnectionError: 연결되지 않은 경우
        """
        if not self._exchange:
            await self.connect()

        message = Message(
            body=event_json.encode("utf-8"),
            delivery_mode=DeliveryMode.PERSISTENT,
            content_type="application/json",
        )

        await self._exchange.publish(message, routing_key="")
