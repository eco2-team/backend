from __future__ import annotations

import json
import logging
from datetime import datetime

from fastapi import Depends
from redis.asyncio import Redis

from domains.auth.core.redis import get_blacklist_redis
from domains.auth.core.security import compute_ttl_seconds, now_utc
from domains.auth.core.jwt import TokenPayload
from domains.auth.services.blacklist_publisher import get_blacklist_publisher

logger = logging.getLogger(__name__)


class TokenBlacklist:
    def __init__(self, redis: Redis = Depends(get_blacklist_redis)):
        self.redis = redis

    async def add(self, payload: TokenPayload, reason: str = "logout") -> None:
        expires_at = datetime.fromtimestamp(payload.exp, tz=now_utc().tzinfo)
        ttl = compute_ttl_seconds(expires_at)
        if ttl <= 0:
            return

        # 1. Store in Redis (primary source of truth)
        data = {
            "user_id": payload.sub,
            "reason": reason,
            "blacklisted_at": now_utc().isoformat(),
            "expires_at": expires_at.isoformat(),
        }
        await self.redis.setex(self._key(payload.jti), ttl, json.dumps(data))

        # 2. Publish event for ext-authz local cache sync
        publisher = get_blacklist_publisher()
        if publisher:
            published = publisher.publish_add(payload.jti, expires_at)
            if published:
                logger.debug(
                    "Blacklist event published",
                    extra={"jti": payload.jti[:8], "reason": reason},
                )
            else:
                logger.warning(
                    "Failed to publish blacklist event (ext-authz will use Redis fallback)",
                    extra={"jti": payload.jti[:8]},
                )

    async def contains(self, jti: str) -> bool:
        return bool(await self.redis.exists(self._key(jti)))

    @staticmethod
    def _key(jti: str) -> str:
        return f"blacklist:{jti}"
