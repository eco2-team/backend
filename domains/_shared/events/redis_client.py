"""Redis 클라이언트 팩토리.

Celery Worker (동기) 와 FastAPI (비동기) 에서 사용하는
Redis 클라이언트를 생성합니다.

설정:
    REDIS_STREAMS_URL: Redis Streams용 URL (기본: REDIS_URL)
    REDIS_URL: 기본 Redis URL

v2 변경사항 (2025-12-26):
    - ConnectionPool 명시적 설정
    - health_check_interval 추가 (연결 상태 자동 체크)
    - retry_on_timeout 활성화
    - 연결 끊김 시 자동 재연결 지원
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

# 환경변수에서 Redis URL 가져오기
# Streams Redis: 이벤트 발행/구독, State KV
_REDIS_STREAMS_URL = os.getenv(
    "REDIS_STREAMS_URL",
    "redis://localhost:6379/0",  # 로컬 개발용 (Streams 전용 Redis)
)

# Cache Redis: 결과 캐싱 (scan:result:{job_id})
_REDIS_CACHE_URL = os.getenv(
    "REDIS_CACHE_URL",
    "redis://localhost:6379/1",  # 로컬 개발용 기본값
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
        retry_on_timeout=True,
        health_check_interval=30,  # 30초마다 연결 상태 체크
    )


_async_redis_client: "aioredis.Redis | None" = None  # type: ignore[type-arg]


async def get_async_redis_client() -> "aioredis.Redis":  # type: ignore[type-arg]
    """비동기 Redis 클라이언트 (FastAPI SSE용).

    FastAPI asyncio event loop에서 사용됩니다.
    redis.asyncio를 사용하여 non-blocking I/O를 수행합니다.

    v2 변경사항:
        - health_check_interval: 30초마다 연결 상태 확인
        - retry_on_timeout: 타임아웃 시 자동 재시도
        - max_connections: 연결 풀 크기 제한

    Note:
        socket_timeout은 XREAD block 타임아웃보다 충분히 커야 합니다.
        AI 답변 생성에 6~10초 소요되므로 60초로 설정.

    Returns:
        비동기 Redis 클라이언트 (싱글톤, ConnectionPool 사용)

    Example:
        >>> from domains._shared.events import get_async_redis_client
        >>> redis_client = await get_async_redis_client()
        >>> await redis_client.xread({"stream:key": "0"}, block=5000)
    """
    global _async_redis_client

    if _async_redis_client is None:
        import redis.asyncio as aioredis

        # ConnectionPool 사용으로 연결 재사용 및 자동 복구
        _async_redis_client = aioredis.from_url(
            _REDIS_STREAMS_URL,
            decode_responses=False,  # 바이트 유지 (Streams 호환)
            socket_timeout=60.0,  # XREAD block(5s) + AI 처리(10s) 여유
            socket_connect_timeout=5.0,
            retry_on_timeout=True,  # 타임아웃 시 자동 재시도
            health_check_interval=30,  # 30초마다 연결 상태 확인
            max_connections=50,  # 연결 풀 크기 (SSE CCU 기준)
        )
        logger.info(
            "async_redis_client_initialized",
            extra={"url": _REDIS_STREAMS_URL, "max_connections": 50},
        )

    return _async_redis_client


async def close_async_redis_client() -> None:
    """비동기 Redis 클라이언트 종료.

    FastAPI shutdown 이벤트에서 호출합니다.
    """
    global _async_redis_client

    if _async_redis_client is not None:
        await _async_redis_client.close()
        logger.info("async_redis_client_closed")
        _async_redis_client = None


async def reset_async_redis_client() -> "aioredis.Redis":  # type: ignore[type-arg]
    """비동기 Redis 클라이언트 재설정.

    연결 오류 발생 시 클라이언트를 재생성합니다.

    Returns:
        새로운 비동기 Redis 클라이언트
    """
    global _async_redis_client

    if _async_redis_client is not None:
        try:
            await _async_redis_client.close()
        except Exception:
            pass
        _async_redis_client = None

    logger.warning("async_redis_client_reset")
    return await get_async_redis_client()


# ─────────────────────────────────────────────────────────────────
# Cache Redis (결과 캐싱용)
# ─────────────────────────────────────────────────────────────────

_async_cache_client: "aioredis.Redis | None" = None  # type: ignore[type-arg]


async def get_async_cache_client() -> "aioredis.Redis":  # type: ignore[type-arg]
    """비동기 Cache Redis 클라이언트.

    Result 캐시 조회용 (scan:result:{job_id}).
    Streams Redis와 분리되어 있음.

    v3 변경사항 (2025-12-29):
        - max_connections: 20 → 100 (600 VU 부하 테스트 대응)
        - Pod당 100 연결 허용 (3 pods × 100 = 300 연결)

    Returns:
        비동기 Cache Redis 클라이언트 (싱글톤)
    """
    global _async_cache_client

    if _async_cache_client is None:
        import redis.asyncio as aioredis

        _async_cache_client = aioredis.from_url(
            _REDIS_CACHE_URL,
            decode_responses=True,  # 문자열 디코딩 (JSON 처리 편의)
            socket_timeout=5.0,
            socket_connect_timeout=5.0,
            retry_on_timeout=True,
            health_check_interval=30,
            max_connections=100,  # 20 → 100 (600 VU 대응)
        )
        logger.info(
            "async_cache_client_initialized",
            extra={"url": _REDIS_CACHE_URL, "max_connections": 100},
        )

    return _async_cache_client


async def close_async_cache_client() -> None:
    """비동기 Cache Redis 클라이언트 종료."""
    global _async_cache_client

    if _async_cache_client is not None:
        await _async_cache_client.close()
        logger.info("async_cache_client_closed")
        _async_cache_client = None
