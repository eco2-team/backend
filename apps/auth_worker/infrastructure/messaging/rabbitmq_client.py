"""RabbitMQ Client.

MQ 연결/채널/메시지 스트림을 담당하는 Infrastructure 컴포넌트입니다.

블로그 참고: https://rooftopsnow.tistory.com/126

| 컴포넌트 | 계층 | 책임 |
|---------|------|------|
| RabbitMQClient | Infrastructure | MQ 연결/채널/메시지 스트림 |
| ConsumerAdapter | Presentation | decode/dispatch/ack-nack |

왜 분리하는가?
- 테스트: ConsumerAdapter는 RabbitMQClient 없이 테스트 가능
- 교체: RabbitMQ → Kafka 전환 시 RabbitMQClient만 교체
- 책임 분리: "연결"과 "디스패칭"은 다른 관심사
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Awaitable, Callable

import aio_pika
from aio_pika import ExchangeType

if TYPE_CHECKING:
    from aio_pika.abc import (
        AbstractChannel,
        AbstractConnection,
        AbstractIncomingMessage,
        AbstractQueue,
    )

logger = logging.getLogger(__name__)


class RabbitMQClient:
    """RabbitMQ 클라이언트.

    MQ 연결과 메시지 스트림을 담당합니다.
    메시지 처리(decode/dispatch/ack)는 ConsumerAdapter에 위임합니다.
    """

    EXCHANGE_NAME = "blacklist.events"  # Fanout exchange (ext-authz 캐시 동기화)
    QUEUE_NAME = "auth.blacklist"  # 1:1 정책 적용

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

    async def connect(self) -> None:
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

        # Queue 선언 (CRD와 동일한 인자)
        self._queue = await self._channel.declare_queue(
            self.QUEUE_NAME,
            durable=True,
            auto_delete=False,
            arguments={
                "x-message-ttl": 86400000,  # 24시간
                "x-dead-letter-exchange": "dlx",
                "x-dead-letter-routing-key": f"dlq.{self.QUEUE_NAME}",
            },
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

    async def start_consuming(
        self,
        callback: Callable[["AbstractIncomingMessage"], Awaitable[None]],
    ) -> None:
        """메시지 소비 시작.

        Args:
            callback: 메시지 처리 콜백 (ConsumerAdapter.on_message)
        """
        if not self._queue:
            raise RuntimeError("Not connected. Call connect() first.")

        # 메시지 소비 시작 (no_ack=False: 수동 ack)
        await self._queue.consume(callback, no_ack=False)

        logger.info("Started consuming messages")

        # 종료 대기
        while not self._shutdown:
            import asyncio

            await asyncio.sleep(1)

    async def close(self) -> None:
        """연결 종료."""
        self._shutdown = True
        if self._connection and not self._connection.is_closed:
            await self._connection.close()
            logger.info("RabbitMQ connection closed")
