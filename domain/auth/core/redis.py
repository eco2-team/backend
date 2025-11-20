from functools import lru_cache

from redis.asyncio import Redis

from domain.auth.core.config import get_settings


def _build_client(url: str) -> Redis:
    return Redis.from_url(url, encoding="utf-8", decode_responses=True)


@lru_cache
def get_blacklist_redis() -> Redis:
    settings = get_settings()
    return _build_client(settings.redis_blacklist_url)


@lru_cache
def get_oauth_state_redis() -> Redis:
    settings = get_settings()
    return _build_client(settings.redis_oauth_state_url)
