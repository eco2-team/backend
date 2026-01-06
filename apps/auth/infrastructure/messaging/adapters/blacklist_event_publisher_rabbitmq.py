"""RabbitMQ Blacklist Event Publisher.

BlacklistEventPublisher 포트의 RabbitMQ 구현체입니다.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import aio_pika
from aio_pika import DeliveryMode, ExchangeType, Message

if TYPE_CHECKING:
    from aio_pika.abc import AbstractChannel, AbstractConnection, AbstractExchange

from apps.auth.domain.value_objects.token_payload import TokenPayload

logger = logging.getLogger(__name__)


class RabbitMQBlacklistEventPublisher:
    """RabbitMQ 기반 블랙리스트 이벤트 발행자.

    BlacklistEventPublisher 인터페이스 구현체입니다.
    Fanout Exchange로 이벤트를 발행하면 auth_worker가 소비합니다.
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
            "RabbitMQ connected for blacklist events",
            extra={"exchange": self.EXCHANGE_NAME},
        )

    async def close(self) -> None:
        """연결 종료."""
        if self._connection and not self._connection.is_closed:
            await self._connection.close()
            logger.debug("RabbitMQ connection closed")

    async def publish_add(
        self,
        payload: TokenPayload,
        reason: str = "logout",
    ) -> None:
        """블랙리스트 추가 이벤트 발행.

        Args:
            payload: 토큰 페이로드
            reason: 블랙리스트 사유
        """
        await self._ensure_connected()

        event = {
            "type": "add",
            "jti": payload.jti,
            "user_id": str(payload.user_id.value),
            "expires_at": datetime.fromtimestamp(payload.exp, tz=timezone.utc).isoformat(),
            "reason": reason,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        await self._publish(event)
        logger.info(
            "Blacklist add event published",
            extra={
                "jti": payload.jti[:8],
                "user_id": str(payload.user_id.value)[:8],
                "reason": reason,
            },
        )

    async def publish_remove(self, jti: str) -> None:
        """블랙리스트 제거 이벤트 발행.

        Args:
            jti: JWT Token ID
        """
        await self._ensure_connected()

        event = {
            "type": "remove",
            "jti": jti,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        await self._publish(event)
        logger.info(
            "Blacklist remove event published",
            extra={"jti": jti[:8]},
        )

    async def _ensure_connected(self) -> None:
        """연결 확인 및 재연결."""
        if not self._connection or self._connection.is_closed:
            await self.connect()

    async def _publish(self, event: dict) -> None:
        """이벤트 발행."""
        if not self._exchange:
            raise RuntimeError("Exchange not initialized")

        message = Message(
            body=json.dumps(event).encode(),
            content_type="application/json",
            delivery_mode=DeliveryMode.PERSISTENT,
        )

        await self._exchange.publish(message, routing_key="")
