"""Message Save Consumer Adapter.

MQ semantics를 담당하는 프로토콜 어댑터.
배치 처리를 위한 특수 로직 포함.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aio_pika.abc import AbstractIncomingMessage

    from chat.presentation.consumer.handler import MessageSaveHandler

logger = logging.getLogger(__name__)


class MessageSaveConsumerAdapter:
    """Message Save Consumer 어댑터.

    배치 처리 특화:
    - 메시지 수신 → Handler 배치에 추가
    - 배치 조건 충족 시 flush
    - 타임아웃 기반 자동 flush
    """

    def __init__(
        self,
        handler: "MessageSaveHandler",
        flush_interval: float = 5.0,
    ) -> None:
        """초기화.

        Args:
            handler: 메시지 핸들러
            flush_interval: 자동 flush 간격 (초)
        """
        self._handler = handler
        self._flush_interval = flush_interval
        self._processed = 0
        self._retried = 0
        self._dropped = 0
        self._flush_task: asyncio.Task | None = None
        self._running = False

    async def start(self) -> None:
        """자동 flush 태스크 시작."""
        self._running = True
        self._flush_task = asyncio.create_task(self._auto_flush_loop())
        logger.info("Consumer adapter started with auto-flush")

    async def stop(self) -> None:
        """Consumer 종료 및 최종 flush."""
        self._running = False

        # 자동 flush 태스크 취소
        if self._flush_task:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass

        # 잔여 배치 flush
        await self._handler.flush()
        logger.info(
            "Consumer adapter stopped",
            extra={"stats": self.stats},
        )

    async def _auto_flush_loop(self) -> None:
        """주기적 배치 flush."""
        while self._running:
            try:
                await asyncio.sleep(self._flush_interval)
                if self._handler.batch_size > 0:
                    await self._handler.flush()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Auto-flush error")

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

            elif result.is_retryable:
                # nack + requeue
                await message.nack(requeue=True)
                self._retried += 1
                logger.warning(
                    "Message requeued for retry",
                    extra={"reason": result.message},
                )

            elif result.should_drop:
                # ack (메시지 버림)
                await message.ack()
                self._dropped += 1
                logger.warning(
                    "Message dropped",
                    extra={"reason": result.message},
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
            "pending_batch": self._handler.batch_size,
        }
