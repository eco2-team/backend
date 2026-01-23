"""LangGraph Checkpointer - Redis Primary + PostgreSQL Async Sync.

Worker는 Redis에만 checkpoint를 저장하고,
별도 프로세스(checkpoint_syncer)가 PostgreSQL로 비동기 동기화.

아키텍처:
```
Worker → AsyncRedisSaver (Redis)
              │
              └─ checkpoint_syncer (별도 프로세스)
                   └─ AsyncPostgresSaver → PostgreSQL
```

이점:
- Worker에서 PostgreSQL connection pool 제거
- PoolTimeout 구조적 제거
- KEDA 스케일링에도 PostgreSQL 영향 없음
"""

from __future__ import annotations

import logging
import random
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from langgraph.checkpoint.base import BaseCheckpointSaver

    from chat_worker.infrastructure.orchestration.langgraph.sync import (
        ReadThroughCheckpointer,
    )

logger = logging.getLogger(__name__)

# Redis checkpoint TTL (분 단위)
DEFAULT_CHECKPOINT_TTL_MINUTES = 1440  # 24시간


async def create_redis_checkpointer(
    redis_url: str,
    ttl_minutes: int = DEFAULT_CHECKPOINT_TTL_MINUTES,
) -> "BaseCheckpointSaver":
    """Redis 기반 LangGraph checkpointer 생성 (sync queue 포함).

    Worker의 primary checkpointer로 사용.
    SyncableRedisSaver가 checkpoint 저장 시 sync queue에 이벤트를 추가하여
    checkpoint_syncer가 PostgreSQL로 동기화할 수 있도록 함.

    Args:
        redis_url: Redis 연결 URL
        ttl_minutes: Checkpoint TTL (분, 기본 24시간=1440분)

    Returns:
        SyncableRedisSaver 인스턴스
    """
    from chat_worker.infrastructure.orchestration.langgraph.sync import (
        SyncableRedisSaver,
    )

    saver = SyncableRedisSaver(
        redis_url=redis_url,
        ttl={"default_ttl": ttl_minutes},
    )
    await saver.asetup()

    logger.info(
        "SyncableRedisSaver created (ttl=%d min)",
        ttl_minutes,
    )
    return saver


async def create_postgres_checkpointer(
    conn_string: str,
    pool_min_size: int = 1,
    pool_max_size: int = 5,
) -> "BaseCheckpointSaver":
    """PostgreSQL checkpointer 생성.

    사용처:
    - checkpoint_syncer: write 전용 (pool_max_size=5)
    - ReadThroughCheckpointer: read-only fallback (pool_max_size=2)

    Args:
        conn_string: PostgreSQL 연결 문자열 (postgresql+asyncpg://...)
        pool_min_size: 풀 최소 연결 수
        pool_max_size: 풀 최대 연결 수

    Returns:
        AsyncPostgresSaver 인스턴스
    """
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    from psycopg_pool import AsyncConnectionPool

    # SQLAlchemy URL → psycopg URL 변환
    psycopg_conn_string = conn_string.replace("postgresql+asyncpg://", "postgresql://")

    pool = AsyncConnectionPool(
        conninfo=psycopg_conn_string,
        min_size=pool_min_size,
        max_size=pool_max_size,
        open=False,
        timeout=30,
        max_lifetime=300 + random.randint(0, 60),
        max_idle=60,
        num_workers=2,
        reconnect_timeout=30,
    )
    await pool.open()

    checkpointer = AsyncPostgresSaver(pool)
    await checkpointer.setup()

    logger.info(
        "PostgreSQL checkpointer created (pool min=%d, max=%d)",
        pool.min_size,
        pool.max_size,
    )
    return checkpointer


async def create_read_through_checkpointer(
    redis_url: str,
    postgres_url: str,
    ttl_minutes: int = DEFAULT_CHECKPOINT_TTL_MINUTES,
    pg_pool_min_size: int = 1,
    pg_pool_max_size: int = 2,
) -> "ReadThroughCheckpointer":
    """Read-Through Checkpointer (Redis Primary + PG Cold Start Fallback).

    Worker의 primary checkpointer로 사용.
    Redis에 checkpoint가 없으면 PostgreSQL에서 읽어 Redis로 promote.

    Temporal Locality (시간적 지역성):
    - Redis TTL 만료 후 재접속한 세션 → PG에서 복원 → Redis에 적재
    - 이후 동일 세션 요청은 Redis에서 직접 서빙
    - 최근 참조된 데이터가 다시 참조될 확률이 높으므로
      promote된 checkpoint는 TTL 내에 재사용될 가능성 높음

    Args:
        redis_url: Redis 연결 URL
        postgres_url: PostgreSQL 연결 URL (read-only fallback)
        ttl_minutes: Checkpoint TTL (분, 기본 24시간=1440분)
        pg_pool_min_size: PG read pool 최소 연결 수 (기본 1)
        pg_pool_max_size: PG read pool 최대 연결 수 (기본 2, cold start만 사용)

    Returns:
        ReadThroughCheckpointer 인스턴스
    """
    from chat_worker.infrastructure.orchestration.langgraph.sync import (
        ReadThroughCheckpointer,
        SyncableRedisSaver,
    )

    # Redis primary (read + write + sync queue)
    redis_saver = SyncableRedisSaver(
        redis_url=redis_url,
        ttl={"default_ttl": ttl_minutes},
    )
    await redis_saver.asetup()

    # PostgreSQL read-only fallback (small pool, cold start only)
    pg_saver = await create_postgres_checkpointer(
        conn_string=postgres_url,
        pool_min_size=pg_pool_min_size,
        pool_max_size=pg_pool_max_size,
    )

    checkpointer = ReadThroughCheckpointer(
        redis_saver=redis_saver,
        pg_saver=pg_saver,
    )

    logger.info(
        "ReadThroughCheckpointer created (redis ttl=%d min, pg pool max=%d)",
        ttl_minutes,
        pg_pool_max_size,
    )
    return checkpointer


async def create_memory_checkpointer() -> "BaseCheckpointSaver":
    """InMemory checkpointer (테스트/로컬 폴백).

    Redis 연결 실패 시 폴백으로 사용.
    프로세스 재시작 시 모든 state 유실.

    Returns:
        MemorySaver 인스턴스
    """
    from langgraph.checkpoint.memory import MemorySaver

    checkpointer = MemorySaver()
    logger.info("InMemory checkpointer created (fallback)")
    return checkpointer
