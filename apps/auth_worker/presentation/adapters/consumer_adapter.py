"""Consumer Adapter.

MQ semantics를 담당하는 프로토콜 어댑터입니다.

블로그 참고: https://rooftopsnow.tistory.com/126

ConsumerAdapter의 책임:
1. 메시지 decode (JSON)
2. Handler 디스패칭
3. CommandResult 기반 ack/nack 결정

RabbitMQClient (Infra)
        │
        │ message stream (bytes)
        ▼
ConsumerAdapter (Presentation)
        │
        │ JSON decoded data
        ▼
Handler (Presentation)
        │
        │ Application DTO
        ▼
Command (Application)
        │
        │ CommandResult
        ▼
ConsumerAdapter
        │
        └── ack / nack / requeue
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aio_pika.abc import AbstractIncomingMessage

    from apps.auth_worker.presentation.handlers.blacklist_handler import (
        BlacklistHandler,
    )

logger = logging.getLogger(__name__)


class ConsumerAdapter:
    """Consumer 어댑터.

    MQ 메시지를 Handler로 디스패칭하고,
    CommandResult에 따라 ack/nack을 결정합니다.
    """

    def __init__(self, handler: "BlacklistHandler") -> None:
        """Initialize.

        Args:
            handler: 메시지 핸들러 (DI)
        """
        self._handler = handler
        self._processed = 0
        self._retried = 0
        self._dropped = 0

    async def on_message(self, message: "AbstractIncomingMessage") -> None:
        """메시지 처리 콜백.

        Args:
            message: RabbitMQ 메시지
        """
        try:
            # 1. Decode
            data = json.loads(message.body.decode())

            # 2. Dispatch to Handler
            result = await self._handler.handle(data)

            # 3. ack/nack 결정
            if result.is_success:
                await message.ack()
                self._processed += 1
                logger.debug(
                    "Message processed",
                    extra={"jti": data.get("jti", "")[:8]},
                )

            elif result.is_retryable:
                # nack + requeue
                await message.nack(requeue=True)
                self._retried += 1
                logger.warning(
                    "Message requeued for retry",
                    extra={
                        "jti": data.get("jti", "")[:8],
                        "reason": result.message,
                    },
                )

            elif result.should_drop:
                # ack (메시지 버림)
                await message.ack()
                self._dropped += 1
                logger.warning(
                    "Message dropped",
                    extra={
                        "jti": data.get("jti", "")[:8],
                        "reason": result.message,
                    },
                )

        except json.JSONDecodeError as e:
            # JSON 파싱 실패 → 버림
            await message.ack()
            self._dropped += 1
            logger.error("Invalid JSON message", extra={"error": str(e)})

        except Exception:
            # 예상치 못한 오류 → requeue
            await message.nack(requeue=True)
            self._retried += 1
            logger.exception("Unexpected error in consumer adapter")

    @property
    def stats(self) -> dict[str, int]:
        """통계 반환."""
        return {
            "processed": self._processed,
            "retried": self._retried,
            "dropped": self._dropped,
        }
