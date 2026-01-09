from __future__ import annotations

import logging

import redis.asyncio as redis
from redis.asyncio import Redis
from redis.asyncio.retry import Retry
from redis.backoff import ExponentialBackoff

from images.core.config import get_settings

logger = logging.getLogger(__name__)

_redis_client: Redis | None = None


def get_upload_redis() -> Redis:
    """Get Redis client with retry and connection pool settings.

    Retry policy (configurable via Settings):
    - ExponentialBackoff with base delay
    - Max retries on connection errors
    - Auto-reconnect on connection failures
    """
    global _redis_client
    if _redis_client is None:
        settings = get_settings()

        # Retry with exponential backoff
        retry = Retry(
            backoff=ExponentialBackoff(base=settings.redis_retry_base_delay),
            retries=settings.redis_retry_attempts,
        )

        _redis_client = redis.from_url(
            settings.redis_url,
            decode_responses=True,
            health_check_interval=settings.redis_health_check_interval,
            retry=retry,
            retry_on_timeout=True,
            retry_on_error=[
                redis.ConnectionError,
                redis.TimeoutError,
                ConnectionResetError,
                ConnectionError,
            ],
            socket_keepalive=True,
            socket_connect_timeout=settings.redis_socket_connect_timeout,
            socket_timeout=settings.redis_socket_timeout,
        )
        logger.info(
            "Redis client initialized",
            extra={
                "health_check_interval": settings.redis_health_check_interval,
                "retry_attempts": settings.redis_retry_attempts,
                "retry_base_delay": settings.redis_retry_base_delay,
                "socket_timeout": settings.redis_socket_timeout,
            },
        )
    return _redis_client


async def close_upload_redis() -> None:
    """Close Redis connection gracefully."""
    global _redis_client
    if _redis_client is not None:
        await _redis_client.close()
        _redis_client = None
        logger.info("Redis client closed")
