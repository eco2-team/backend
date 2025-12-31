"""Auth Worker Entry Point.

블랙리스트 이벤트를 소비하여 Redis에 저장하는 워커입니다.

Architecture:
    RabbitMQ (blacklist.events)
        │
        └── auth-worker (이 모듈)
                │
                ├── PersistBlacklistCommand
                │       │
                │       └── RedisBlacklistStore
                │               │
                │               └── Redis (blacklist:{jti})
                │
                └── ext-authz가 Redis에서 조회

Run:
    python -m apps.auth_worker.main
"""

from __future__ import annotations

import asyncio
import logging
import signal
from typing import Any

from apps.auth_worker.application.common.dto.blacklist_event import BlacklistEvent
from apps.auth_worker.setup.config import get_settings
from apps.auth_worker.setup.dependencies import Container
from apps.auth_worker.setup.logging import setup_logging

logger = logging.getLogger(__name__)


class AuthWorker:
    """Auth Worker.

    블랙리스트 이벤트를 소비하여 Redis에 저장합니다.
    """

    def __init__(self) -> None:
        self._container = Container()
        self._shutdown = False
        self._processed = 0
        self._errors = 0

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

        # 이벤트 소비 시작
        try:
            await self._container.consumer.start(self._handle_event)
        finally:
            await self._cleanup()

    def _handle_shutdown(self) -> None:
        """Graceful shutdown 핸들러."""
        logger.info("Shutdown signal received")
        self._shutdown = True

    async def _handle_event(self, data: dict[str, Any]) -> None:
        """이벤트 핸들러.

        Args:
            data: 이벤트 데이터
        """
        try:
            event = BlacklistEvent.from_dict(data)
            await self._container.persist_command.execute(event)
            self._processed += 1
        except Exception:
            self._errors += 1
            logger.exception(
                "Error handling event",
                extra={"data": data},
            )
            raise

    async def _cleanup(self) -> None:
        """리소스 정리."""
        logger.info(
            "Shutting down",
            extra={
                "processed": self._processed,
                "errors": self._errors,
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
