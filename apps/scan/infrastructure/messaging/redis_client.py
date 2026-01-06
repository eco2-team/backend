"""Redis 클라이언트 팩토리.

scan API 전용 - domains 의존성 제거.

두 종류의 Redis 클라이언트:
- Streams Redis: 이벤트 발행/구독, State KV
- Cache Redis: 결과 캐싱, 멱등성 캐시
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import redis
    import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────
# 환경변수
# ─────────────────────────────────────────────────────────────────

_REDIS_STREAMS_URL = os.getenv(
    "REDIS_STREAMS_URL",
    "redis://localhost:6379/0",
)

_REDIS_CACHE_URL = os.getenv(
    "REDIS_CACHE_URL",
    "redis://localhost:6379/1",
)


# ─────────────────────────────────────────────────────────────────
# Streams Redis (이벤트 발행)
# ─────────────────────────────────────────────────────────────────


@lru_cache(maxsize=1)
def get_sync_streams_client() -> "redis.Redis[bytes]":
    """동기 Redis Streams 클라이언트.

    queued 이벤트 발행용 (작업 제출 시).

    Returns:
        동기 Redis 클라이언트 (싱글톤)
    """
    import redis

    return redis.from_url(
        _REDIS_STREAMS_URL,
        decode_responses=False,
        socket_timeout=5.0,
        socket_connect_timeout=5.0,
        retry_on_timeout=True,
        health_check_interval=30,
    )


_async_streams_client: "aioredis.Redis | None" = None


async def get_async_streams_client() -> "aioredis.Redis":
    """비동기 Redis Streams 클라이언트.

    State KV 조회용.

    Returns:
        비동기 Redis 클라이언트 (싱글톤)
    """
    global _async_streams_client

    if _async_streams_client is None:
        import redis.asyncio as aioredis

        _async_streams_client = aioredis.from_url(
            _REDIS_STREAMS_URL,
            decode_responses=False,
            socket_timeout=60.0,
            socket_connect_timeout=5.0,
            retry_on_timeout=True,
            health_check_interval=30,
            max_connections=50,
        )
        logger.info(
            "async_streams_client_initialized",
            extra={"url": _REDIS_STREAMS_URL},
        )

    return _async_streams_client


async def close_async_streams_client() -> None:
    """비동기 Streams 클라이언트 종료."""
    global _async_streams_client

    if _async_streams_client is not None:
        await _async_streams_client.close()
        logger.info("async_streams_client_closed")
        _async_streams_client = None


# ─────────────────────────────────────────────────────────────────
# Cache Redis (결과 캐싱, 멱등성 캐시)
# ─────────────────────────────────────────────────────────────────


_async_cache_client: "aioredis.Redis | None" = None


async def get_async_cache_client() -> "aioredis.Redis":
    """비동기 Cache Redis 클라이언트.

    결과 캐시, 멱등성 캐시 조회용.

    Returns:
        비동기 Redis 클라이언트 (싱글톤)
    """
    global _async_cache_client

    if _async_cache_client is None:
        import redis.asyncio as aioredis

        _async_cache_client = aioredis.from_url(
            _REDIS_CACHE_URL,
            decode_responses=True,  # JSON 처리 편의
            socket_timeout=5.0,
            socket_connect_timeout=5.0,
            retry_on_timeout=True,
            health_check_interval=30,
            max_connections=100,
        )
        logger.info(
            "async_cache_client_initialized",
            extra={"url": _REDIS_CACHE_URL},
        )

    return _async_cache_client


async def close_async_cache_client() -> None:
    """비동기 Cache 클라이언트 종료."""
    global _async_cache_client

    if _async_cache_client is not None:
        await _async_cache_client.close()
        logger.info("async_cache_client_closed")
        _async_cache_client = None
