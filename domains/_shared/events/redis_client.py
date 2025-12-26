"""Redis 클라이언트 팩토리.

Celery Worker (동기) 와 FastAPI (비동기) 에서 사용하는
Redis 클라이언트를 생성합니다.

설정:
    REDIS_STREAMS_URL: Redis Streams용 URL (기본: REDIS_URL)
    REDIS_URL: 기본 Redis URL
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import redis
    import redis.asyncio as aioredis

# 환경변수에서 Redis Streams URL 가져오기
# 로컬 개발: localhost, K8s: rfr-streams-redis.redis.svc.cluster.local
_REDIS_STREAMS_URL = os.getenv(
    "REDIS_STREAMS_URL",
    "redis://localhost:6379/0",  # 로컬 개발용 (Streams 전용 Redis)
)


@lru_cache(maxsize=1)
def get_sync_redis_client() -> "redis.Redis[bytes]":
    """동기 Redis 클라이언트 (Celery Worker용).

    Celery gevent pool에서 사용됩니다.
    gevent가 socket I/O를 자동으로 greenlet 전환합니다.

    Returns:
        동기 Redis 클라이언트 (싱글톤)

    Example:
        >>> from domains._shared.events import get_sync_redis_client
        >>> redis_client = get_sync_redis_client()
        >>> redis_client.xadd("stream:key", {"field": "value"})
    """
    import redis

    return redis.from_url(
        _REDIS_STREAMS_URL,
        decode_responses=False,  # 바이트 유지 (Streams 호환)
        socket_timeout=5.0,
        socket_connect_timeout=5.0,
    )


_async_redis_client: "aioredis.Redis | None" = None  # type: ignore[type-arg]


async def get_async_redis_client() -> "aioredis.Redis":  # type: ignore[type-arg]
    """비동기 Redis 클라이언트 (FastAPI SSE용).

    FastAPI asyncio event loop에서 사용됩니다.
    redis.asyncio를 사용하여 non-blocking I/O를 수행합니다.

    Returns:
        비동기 Redis 클라이언트 (싱글톤)

    Example:
        >>> from domains._shared.events import get_async_redis_client
        >>> redis_client = await get_async_redis_client()
        >>> await redis_client.xread({"stream:key": "0"}, block=5000)
    """
    global _async_redis_client

    if _async_redis_client is None:
        import redis.asyncio as aioredis

        _async_redis_client = aioredis.from_url(
            _REDIS_STREAMS_URL,
            decode_responses=False,  # 바이트 유지 (Streams 호환)
            socket_timeout=5.0,
            socket_connect_timeout=5.0,
        )

    return _async_redis_client


async def close_async_redis_client() -> None:
    """비동기 Redis 클라이언트 종료.

    FastAPI shutdown 이벤트에서 호출합니다.
    """
    global _async_redis_client

    if _async_redis_client is not None:
        await _async_redis_client.close()
        _async_redis_client = None
