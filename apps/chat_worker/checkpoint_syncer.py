"""Chat Checkpoint Syncer.

Redis의 LangGraph checkpoint를 PostgreSQL로 비동기 동기화.
chat_worker 이미지의 별도 entrypoint로 실행.

실행:
    python -m chat_worker.checkpoint_syncer

아키텍처:
    Worker → Redis (SyncableRedisSaver, sync queue에 이벤트 추가)
                │
                └─ 이 프로세스 (CheckpointSyncService)
                     └─ BRPOP으로 sync queue 소비
                          └─ AsyncPostgresSaver → PostgreSQL
"""

from __future__ import annotations

import asyncio
import logging
import signal
import sys

from chat_worker.setup.config import get_settings


def configure_logging() -> None:
    """로깅 설정."""
    settings = get_settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stdout,
    )


async def main() -> None:
    """Syncer 메인 루프."""
    settings = get_settings()

    if not settings.syncer_postgres_url:
        logging.error(
            "CHAT_WORKER_SYNCER_POSTGRES_URL is not configured. "
            "Checkpoint syncer cannot start without PostgreSQL URL."
        )
        sys.exit(1)

    from chat_worker.infrastructure.orchestration.langgraph.sync import (
        CheckpointSyncService,
    )

    logger = logging.getLogger(__name__)
    logger.info("Starting checkpoint syncer...")

    service = await CheckpointSyncService.create(
        redis_url=settings.redis_url,
        postgres_url=settings.syncer_postgres_url,
        pg_pool_min_size=settings.syncer_pg_pool_min_size,
        pg_pool_max_size=settings.syncer_pg_pool_max_size,
        batch_size=settings.syncer_batch_size,
        drain_timeout=settings.syncer_interval,
        checkpoint_ttl_minutes=settings.checkpoint_ttl_minutes,
    )

    stop_event = asyncio.Event()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop_event.set)

    logger.info(
        "Checkpoint syncer ready (postgres=%s, batch_size=%d, interval=%.1fs)",
        settings.syncer_postgres_url[:30] + "...",
        settings.syncer_batch_size,
        settings.syncer_interval,
    )

    try:
        await service.run(stop_event)
    finally:
        await service.close()
        logger.info("Checkpoint syncer stopped gracefully")


if __name__ == "__main__":
    configure_logging()
    asyncio.run(main())
