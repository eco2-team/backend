"""Dependency Injection.

FastAPI 의존성 주입 팩토리.
Info API는 읽기 전용 - 캐시 → Postgres Fallback.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

import asyncpg
from redis.asyncio import Redis

from info.application.commands.fetch_news_command import FetchNewsCommand
from info.infrastructure.cache.redis_news_cache import RedisNewsCache
from info.infrastructure.persistence.postgres_news_repository import (
    PostgresNewsRepository,
)
from info.setup.config import get_settings

# Connection Pool (싱글톤)
_pg_pool: asyncpg.Pool | None = None
_redis: Redis | None = None


async def get_pg_pool() -> asyncpg.Pool | None:
    """PostgreSQL connection pool (싱글톤).

    database_url이 설정되지 않으면 None 반환 (Fallback 비활성화).
    """
    global _pg_pool
    settings = get_settings()

    if not settings.database_url:
        return None

    if _pg_pool is None:
        # asyncpg는 postgresql:// 또는 postgres:// 만 지원
        # SQLAlchemy 스타일 postgresql+asyncpg:// 변환
        dsn = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
        _pg_pool = await asyncpg.create_pool(
            dsn,
            min_size=2,
            max_size=10,
        )
    return _pg_pool


async def get_redis() -> Redis:
    """Redis client (싱글톤)."""
    global _redis
    if _redis is None:
        settings = get_settings()
        _redis = Redis.from_url(settings.redis_url, decode_responses=True)
    return _redis


async def get_fetch_news_command() -> AsyncGenerator[FetchNewsCommand, None]:
    """FetchNewsCommand 의존성 주입.

    FastAPI Depends에서 사용.
    Read-only: Redis 캐시 → Postgres Fallback
    """
    settings = get_settings()

    # Redis (Primary)
    redis = await get_redis()
    cache = RedisNewsCache(redis=redis, ttl=settings.news_cache_ttl)

    # Postgres (Fallback) - optional
    pg_pool = await get_pg_pool()
    repository = PostgresNewsRepository(pool=pg_pool) if pg_pool else None

    # Command (ReadOnly UseCase)
    yield FetchNewsCommand(
        news_cache=cache,
        news_repository=repository,
    )


async def cleanup() -> None:
    """리소스 정리."""
    global _pg_pool, _redis

    if _pg_pool:
        await _pg_pool.close()
        _pg_pool = None

    if _redis:
        await _redis.aclose()
        _redis = None


@asynccontextmanager
async def lifespan_context():
    """FastAPI lifespan context manager."""
    # Startup
    yield
    # Shutdown
    await cleanup()
