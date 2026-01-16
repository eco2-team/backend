"""Chat Worker Main Entry Point."""

from __future__ import annotations

import asyncio
import logging
import sys

from chat_worker.setup.broker import shutdown, startup
from chat_worker.presentation.amqp import health_check, process_chat  # noqa: F401

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

logger = logging.getLogger(__name__)


async def main():
    """Worker 실행."""
    logger.info("Starting Chat Worker...")

    try:
        await startup()
        logger.info("Worker ready. Waiting for tasks...")

        # 무한 대기 (Taskiq가 broker를 통해 태스크 수신)
        while True:
            await asyncio.sleep(3600)

    except KeyboardInterrupt:
        logger.info("Shutdown requested")
    finally:
        await shutdown()
        logger.info("Chat Worker stopped")


if __name__ == "__main__":
    asyncio.run(main())
