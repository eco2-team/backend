from __future__ import annotations

import redis.asyncio as redis
from redis.asyncio import Redis

from domains.chat.core.config import get_settings

_session_client: Redis | None = None


def get_session_redis() -> Redis:
    global _session_client
    if _session_client is None:
        settings = get_settings()
        _session_client = redis.from_url(
            settings.redis_url,
            decode_responses=True,
        )
    return _session_client
