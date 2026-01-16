"""Redis Streams Consumer Adapter.

Event-First Architecture: Redis Streams에서 persistence 이벤트를 소비하여
PostgreSQL에 저장하는 어댑터.

RabbitMQ 기반 adapter.py와 유사하지만 Redis Streams semantics 적용:
- Consumer Group 기반 at-least-once 보장
- XACK로 메시지 확인
- 자동 재시도 (ACK 안된 메시지)
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from chat.infrastructure.messaging.redis_streams_consumer import (
        ChatPersistenceConsumer,
    )
    from chat.presentation.consumer.handler import MessageSaveHandler

logger = logging.getLogger(__name__)


class RedisStreamsConsumerAdapter:
    """Redis Streams Consumer 어댑터.

    ChatPersistenceConsumer와 MessageSaveHandler를 연결.

    Flow:
        ChatPersistenceConsumer (Redis Streams XREADGROUP)
            ↓ persistence dict
        RedisStreamsConsumerAdapter (this)
            ↓ validate & dispatch
        MessageSaveHandler (batch accumulation)
            ↓ batch flush
        SaveMessagesCommand (PostgreSQL write)
    """

    def __init__(
        self,
        consumer: "ChatPersistenceConsumer",
        handler: "MessageSaveHandler",
        flush_interval: float = 5.0,
    ) -> None:
        """초기화.

        Args:
            consumer: Redis Streams Consumer
            handler: 메시지 저장 핸들러
            flush_interval: 자동 flush 간격 (초)
        """
        self._consumer = consumer
        self._handler = handler
        self._flush_interval = flush_interval
        self._processed = 0
        self._failed = 0
        self._dropped = 0
        self._flush_task: asyncio.Task | None = None
        self._running = False

    async def start(self) -> None:
        """Consumer 시작.

        1. Consumer Group 설정
        2. 자동 flush 태스크 시작
        """
        await self._consumer.setup()
        self._running = True
        self._flush_task = asyncio.create_task(self._auto_flush_loop())
        logger.info(
            "Redis Streams consumer adapter started",
            extra={"flush_interval": self._flush_interval},
        )

    async def run(self) -> None:
        """Consumer 루프 실행.

        blocking call - 종료될 때까지 실행.
        """
        await self._consumer.consume(self._process_persistence)

    async def stop(self) -> None:
        """Consumer 종료 및 최종 flush."""
        self._running = False

        # Consumer shutdown
        await self._consumer.shutdown()

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
            "Redis Streams consumer adapter stopped",
            extra={"stats": self.stats},
        )

    async def _process_persistence(self, persistence: dict[str, Any]) -> bool:
        """Persistence 데이터 처리.

        ChatPersistenceConsumer의 콜백으로 호출됨.

        Args:
            persistence: done 이벤트의 persistence 데이터
                {
                    "conversation_id": str,
                    "user_id": str,
                    "user_message": str,
                    "user_message_created_at": str (ISO),
                    "assistant_message": str,
                    "assistant_message_created_at": str (ISO),
                    "intent": str | None,
                    "metadata": dict | None,
                }

        Returns:
            성공 여부 (True면 ACK)
        """
        try:
            result = await self._handler.handle(persistence)

            if result.is_success:
                self._processed += 1
                return True
            elif result.should_drop:
                self._dropped += 1
                logger.warning(
                    "Message dropped",
                    extra={"reason": result.message},
                )
                # drop도 ACK (재처리 방지)
                return True
            else:
                # 재시도 필요
                self._failed += 1
                logger.warning(
                    "Message processing failed, will retry",
                    extra={"reason": result.message},
                )
                return False

        except Exception:
            self._failed += 1
            logger.exception("Unexpected error processing persistence data")
            return False

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

    @property
    def stats(self) -> dict[str, int]:
        """통계 반환."""
        return {
            "processed": self._processed,
            "failed": self._failed,
            "dropped": self._dropped,
            "pending_batch": self._handler.batch_size,
        }
