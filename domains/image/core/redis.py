from __future__ import annotations

import redis.asyncio as redis
from redis.asyncio import Redis

from domains.image.core.config import get_settings

_redis_client: Redis | None = None


def get_upload_redis() -> Redis:
    global _redis_client
    if _redis_client is None:
        settings = get_settings()
        _redis_client = redis.from_url(
            settings.redis_url,
            decode_responses=True,
        )
    return _redis_client
