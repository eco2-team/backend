"""Chat Persistence Consumer Entry Point.

Event-First Architecture: Redis Streams에서 done 이벤트를 소비하여 PostgreSQL에 저장.

Architecture:
    Redis Streams (chat:events:{shard})
        │
        │ Consumer Group: chat-persistence
        ▼
    ChatPersistenceConsumer (Infrastructure)
        │
        │ persistence dict (from done event)
        ▼
    RedisStreamsConsumerAdapter (Presentation)
        │
        │ validate & batch
        ▼
    MessageSaveHandler (Presentation)
        │
        │ batch flush → Application DTO
        ▼
    SaveMessagesCommand (Application)
        │
        │ Result (PostgreSQL write)
        ▼
    RedisStreamsConsumerAdapter
        │
        └── XACK (on success)

Run:
    python -m chat.consumer
"""

from __future__ import annotations

import asyncio
import logging
import signal

from chat.setup.config import get_settings
from chat.setup.consumer_dependencies import ConsumerContainer

logger = logging.getLogger(__name__)


def setup_logging() -> None:
    """로깅 설정."""
    settings = get_settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level),
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )


class ChatPersistenceConsumer:
    """Chat Persistence Consumer.

    Redis Streams에서 done 이벤트의 persistence 데이터를 읽어 PostgreSQL에 저장.

    Event-First Architecture:
    - Worker: done 이벤트에 persistence 데이터 포함하여 Redis Streams에 발행
    - Event Router: SSE fan-out (Consumer Group: event-router)
    - DB Consumer: PostgreSQL 저장 (Consumer Group: chat-persistence)

    main.py의 책임:
    - DI 설정
    - 연결 관리 (Redis, DB)
    - Consumer 시작/종료
    - Graceful shutdown

    배치 처리:
    - 100개 메시지 또는 5초 타임아웃 시 flush
    - 자동 flush 루프로 타임아웃 보장
    """

    def __init__(self) -> None:
        self._container = ConsumerContainer()
        self._shutdown = False

    async def start(self) -> None:
        """Consumer 시작."""
        settings = get_settings()
        logger.info(
            "Chat Persistence Consumer starting",
            extra={
                "service_name": settings.service_name,
                "env": settings.environment,
            },
        )

        # 의존성 초기화
        await self._container.init()
        logger.info("Dependencies initialized")

        # 시그널 핸들러 등록
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, self._handle_shutdown)

        # Consumer Adapter 시작 (Consumer Group 설정 + 자동 flush 루프)
        await self._container.consumer_adapter.start()

        # Redis Streams 소비 시작 (blocking)
        try:
            await self._container.consumer_adapter.run()
        finally:
            await self._cleanup()

    def _handle_shutdown(self) -> None:
        """Graceful shutdown 핸들러."""
        logger.info("Shutdown signal received")
        self._shutdown = True

    async def _cleanup(self) -> None:
        """리소스 정리."""
        stats = self._container.consumer_adapter.stats
        logger.info(
            "Shutting down",
            extra={
                "processed": stats["processed"],
                "failed": stats["failed"],
                "dropped": stats["dropped"],
                "pending_batch": stats["pending_batch"],
            },
        )
        await self._container.close()
        logger.info("Chat Persistence Consumer stopped")


async def main() -> None:
    """Entry point."""
    setup_logging()
    consumer = ChatPersistenceConsumer()
    await consumer.start()


if __name__ == "__main__":
    asyncio.run(main())
