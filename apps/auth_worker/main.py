"""Auth Worker Entry Point.

블랙리스트 이벤트를 소비하여 Redis에 저장하는 워커입니다.

블로그 참고: https://rooftopsnow.tistory.com/126

Architecture:
    RabbitMQClient (Infrastructure)
        │
        │ message stream
        ▼
    ConsumerAdapter (Presentation)
        │
        │ JSON decoded data
        ▼
    BlacklistHandler (Presentation)
        │
        │ Application DTO
        ▼
    PersistBlacklistCommand (Application)
        │
        │ CommandResult
        ▼
    ConsumerAdapter
        │
        └── ack / nack / requeue

Run:
    python -m apps.auth_worker.main
"""

from __future__ import annotations

import asyncio
import logging
import signal

from apps.auth_worker.setup.config import get_settings
from apps.auth_worker.setup.dependencies import Container
from apps.auth_worker.setup.logging import setup_logging

logger = logging.getLogger(__name__)


class AuthWorker:
    """Auth Worker.

    블랙리스트 이벤트를 소비하여 Redis에 저장합니다.

    main.py의 책임:
    - DI 설정
    - 연결 관리 (Redis, MQ)
    - Consumer 시작/종료
    - Graceful shutdown

    main.py의 비책임:
    - 메시지 파싱 (ConsumerAdapter)
    - 업무 로직 (Command)
    - ack/nack 결정 (ConsumerAdapter)
    """

    def __init__(self) -> None:
        self._container = Container()
        self._shutdown = False

    async def start(self) -> None:
        """워커 시작."""
        settings = get_settings()
        logger.info(
            "Auth Worker starting",
            extra={
                "service_name": settings.service_name,
                "service_version": settings.service_version,
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

        # MQ 연결
        await self._container.rabbitmq_client.connect()

        # 이벤트 소비 시작
        try:
            await self._container.rabbitmq_client.start_consuming(
                self._container.consumer_adapter.on_message
            )
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
                "retried": stats["retried"],
                "dropped": stats["dropped"],
            },
        )
        await self._container.close()
        logger.info("Auth Worker stopped")


async def main() -> None:
    """Entry point."""
    setup_logging()
    worker = AuthWorker()
    await worker.start()


if __name__ == "__main__":
    asyncio.run(main())
