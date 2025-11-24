from __future__ import annotations

import asyncio
from typing import Any

import redis.asyncio as redis

from domains.location.core.config import get_settings


class RedisCache:
    """Simple Redis wrapper for caching Location metrics."""

    _client: redis.Redis | None = None

    @classmethod
    def get_client(cls) -> redis.Redis:
        if cls._client is None:
            settings = get_settings()
            cls._client = redis.from_url(settings.redis_url, decode_responses=True)
        return cls._client

    @classmethod
    async def get(cls, key: str) -> Any:
        client = cls.get_client()
        return await client.get(key)

    @classmethod
    async def set(cls, key: str, value: Any, ex: int) -> None:
        client = cls.get_client()
        await client.setex(key, ex, value)

    @classmethod
    async def close(cls) -> None:
        if cls._client:
            await cls._client.close()
            cls._client = None

