"""Redis Client Factory."""

from __future__ import annotations

import logging

from redis.asyncio import Redis

from chat.setup.config import get_settings

logger = logging.getLogger(__name__)

_redis: Redis | None = None


async def get_redis_client() -> Redis:
    """Redis 클라이언트 싱글톤."""
    global _redis
    if _redis is None:
        settings = get_settings()
        _redis = Redis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
        )
        logger.info("Redis connected: %s", settings.redis_url)
    return _redis
