"""RabbitMQ Consumer Client.

메시지 저장 큐를 소비하는 Infrastructure 컴포넌트.
Topology Operator가 생성한 Exchange/Queue 사용.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Awaitable, Callable

import aio_pika

if TYPE_CHECKING:
    from aio_pika.abc import (
        AbstractChannel,
        AbstractConnection,
        AbstractIncomingMessage,
        AbstractQueue,
    )

logger = logging.getLogger(__name__)


class MessageSaveConsumerClient:
    """메시지 저장 Consumer 클라이언트.

    chat.save_messages 큐에서 메시지를 소비합니다.
    Topology Operator가 Exchange/Queue를 이미 생성했으므로
    연결 후 큐 참조만 획득합니다.
    """

    QUEUE_NAME = "chat.save_messages"

    def __init__(self, amqp_url: str, prefetch_count: int = 100) -> None:
        """초기화.

        Args:
            amqp_url: RabbitMQ 연결 URL
            prefetch_count: 한 번에 가져올 메시지 수 (배치 처리용)
        """
        self._amqp_url = amqp_url
        self._prefetch_count = prefetch_count
        self._connection: AbstractConnection | None = None
        self._channel: AbstractChannel | None = None
        self._queue: AbstractQueue | None = None
        self._shutdown = False

    async def connect(self) -> None:
        """RabbitMQ 연결."""
        self._connection = await aio_pika.connect_robust(self._amqp_url)
        self._channel = await self._connection.channel()

        # Prefetch 설정 (배치 처리를 위해 높게 설정)
        await self._channel.set_qos(prefetch_count=self._prefetch_count)

        # Queue 참조 획득 (Topology Operator가 이미 생성함)
        # passive=True: 큐가 없으면 에러
        self._queue = await self._channel.get_queue(self.QUEUE_NAME)

        logger.info(
            "RabbitMQ consumer connected",
            extra={
                "queue": self.QUEUE_NAME,
                "prefetch": self._prefetch_count,
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

        logger.info("Started consuming messages from %s", self.QUEUE_NAME)

        # 종료 대기
        while not self._shutdown:
            await asyncio.sleep(1)

    async def close(self) -> None:
        """연결 종료."""
        self._shutdown = True
        if self._connection and not self._connection.is_closed:
            await self._connection.close()
            logger.info("RabbitMQ consumer connection closed")
