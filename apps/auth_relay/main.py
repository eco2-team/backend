"""Auth Relay Entry Point.

Redis Outbox에서 실패한 블랙리스트 이벤트를 RabbitMQ로 재발행하는 워커입니다.

Architecture:
    RedisOutboxReader (Infrastructure)
        │
        │ event_json (RPOP)
        ▼
    RelayLoop (Presentation)
        │
        │ event_json
        ▼
    RelayEventCommand (Application)
        │
        │ RelayResult
        ▼
    RelayLoop
        │
        └── SUCCESS: continue
            RETRYABLE: push_back (LPUSH)
            DROP: push_to_dlq

Run:
    python -m apps.auth_relay.main
"""

from __future__ import annotations

import asyncio
import logging
import signal

from apps.auth_relay.setup.config import get_settings
from apps.auth_relay.setup.dependencies import Container
from apps.auth_relay.setup.logging import setup_logging

logger = logging.getLogger(__name__)


class AuthRelay:
    """Auth Relay Worker.

    Redis Outbox에서 실패한 이벤트를 RabbitMQ로 재발행합니다.
    """

    def __init__(self) -> None:
        self._container = Container()
        self._shutdown = False

    async def start(self) -> None:
        """워커 시작."""
        settings = get_settings()
        logger.info(
            "Auth Relay starting",
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

        # Relay 루프 시작
        try:
            await self._container.relay_loop.run()
        finally:
            await self._cleanup()

    def _handle_shutdown(self) -> None:
        """Graceful shutdown 핸들러."""
        logger.info("Shutdown signal received")
        self._container.relay_loop.stop()

    async def _cleanup(self) -> None:
        """리소스 정리."""
        stats = self._container.relay_loop.stats
        logger.info(
            "Shutting down",
            extra={
                "processed": stats["processed"],
                "failed": stats["failed"],
            },
        )
        await self._container.close()
        logger.info("Auth Relay stopped")


async def main() -> None:
    """Entry point."""
    setup_logging()
    relay = AuthRelay()
    await relay.start()


if __name__ == "__main__":
    asyncio.run(main())
