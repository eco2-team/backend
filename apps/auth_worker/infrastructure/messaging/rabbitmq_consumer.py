"""RabbitMQ Consumer.

RabbitMQ에서 블랙리스트 이벤트를 소비하는 구현체입니다.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING, Any, Awaitable, Callable

import aio_pika
from aio_pika import ExchangeType

if TYPE_CHECKING:
    from aio_pika.abc import AbstractChannel, AbstractConnection, AbstractQueue

logger = logging.getLogger(__name__)


class RabbitMQConsumer:
    """RabbitMQ 이벤트 소비자.

    EventConsumer 인터페이스 구현체입니다.
    Fanout Exchange에서 블랙리스트 이벤트를 소비합니다.
    """

    EXCHANGE_NAME = "blacklist.events"
    QUEUE_NAME = "auth-worker.blacklist"

    def __init__(self, amqp_url: str) -> None:
        """Initialize.

        Args:
            amqp_url: RabbitMQ 연결 URL
        """
        self._amqp_url = amqp_url
        self._connection: AbstractConnection | None = None
        self._channel: AbstractChannel | None = None
        self._queue: AbstractQueue | None = None
        self._shutdown = False

    async def start(
        self,
        handler: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None:
        """이벤트 소비 시작.

        Args:
            handler: 이벤트 핸들러 콜백
        """
        await self._connect()
        await self._consume(handler)

    async def stop(self) -> None:
        """이벤트 소비 중지."""
        self._shutdown = True
        if self._connection and not self._connection.is_closed:
            await self._connection.close()
            logger.info("RabbitMQ connection closed")

    async def _connect(self) -> None:
        """RabbitMQ 연결."""
        self._connection = await aio_pika.connect_robust(self._amqp_url)
        self._channel = await self._connection.channel()

        # Prefetch 설정 (한 번에 처리할 메시지 수)
        await self._channel.set_qos(prefetch_count=10)

        # Fanout Exchange 선언
        exchange = await self._channel.declare_exchange(
            self.EXCHANGE_NAME,
            ExchangeType.FANOUT,
            durable=True,
        )

        # Queue 선언 (durable, auto-delete=False)
        self._queue = await self._channel.declare_queue(
            self.QUEUE_NAME,
            durable=True,
            auto_delete=False,
        )

        # Exchange에 Queue 바인딩
        await self._queue.bind(exchange)

        logger.info(
            "RabbitMQ connected",
            extra={
                "exchange": self.EXCHANGE_NAME,
                "queue": self.QUEUE_NAME,
            },
        )

    async def _consume(
        self,
        handler: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None:
        """메시지 소비 루프."""
        if not self._queue:
            raise RuntimeError("Queue not initialized")

        async with self._queue.iterator() as queue_iter:
            async for message in queue_iter:
                if self._shutdown:
                    break

                async with message.process():
                    try:
                        data = json.loads(message.body.decode())
                        await handler(data)
                        logger.debug(
                            "Message processed",
                            extra={"jti": data.get("jti", "")[:8]},
                        )
                    except json.JSONDecodeError as e:
                        logger.error(
                            "Invalid JSON message",
                            extra={"error": str(e)},
                        )
                    except Exception:
                        logger.exception("Error processing message")
                        # 메시지는 ack되지만 에러 로깅
                        # DLQ 처리가 필요하면 여기서 구현
