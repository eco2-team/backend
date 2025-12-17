from __future__ import annotations

import redis.asyncio as redis
from redis.asyncio import Redis

from domains.chat.core.config import get_settings

# Redis connection pool health check interval (seconds)
# Prevents "Connection closed by server" errors from idle connections
HEALTH_CHECK_INTERVAL = 30

_session_client: Redis | None = None


def get_session_redis() -> Redis:
    global _session_client
    if _session_client is None:
        settings = get_settings()
        _session_client = redis.from_url(
            settings.redis_url,
            decode_responses=True,
            health_check_interval=HEALTH_CHECK_INTERVAL,
        )
    return _session_client
