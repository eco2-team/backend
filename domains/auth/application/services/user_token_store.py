from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import Depends
from pydantic import BaseModel
from redis.asyncio import Redis

from domains.auth.infrastructure.redis import get_blacklist_redis
from domains.auth.infrastructure.auth.security import compute_ttl_seconds


class TokenMetadata(BaseModel):
    jti: str
    user_id: uuid.UUID
    issued_at: datetime
    expires_at: datetime
    device_id: Optional[str] = None
    user_agent: Optional[str] = None


class UserTokenStore:
    def __init__(self, redis: Redis = Depends(get_blacklist_redis)):
        self.redis = redis

    async def register(
        self,
        *,
        user_id: uuid.UUID,
        jti: str,
        issued_at: int,
        expires_at: int,
        device_id: Optional[str],
        user_agent: Optional[str],
    ) -> None:
        meta = TokenMetadata(
            jti=jti,
            user_id=user_id,
            issued_at=datetime.fromtimestamp(issued_at, tz=timezone.utc),
            expires_at=datetime.fromtimestamp(expires_at, tz=timezone.utc),
            device_id=device_id,
            user_agent=user_agent,
        )
        ttl = max(compute_ttl_seconds(meta.expires_at), 1)
        await self.redis.sadd(self._user_key(user_id), jti)
        await self.redis.expire(self._user_key(user_id), ttl)
        await self.redis.setex(self._meta_key(jti), ttl, meta.model_dump_json())

    async def remove(self, user_id: uuid.UUID, jti: str) -> None:
        await self.redis.srem(self._user_key(user_id), jti)
        await self.redis.delete(self._meta_key(jti))

    async def list(self, user_id: uuid.UUID) -> list[TokenMetadata]:
        jtis = await self.redis.smembers(self._user_key(user_id))
        if not jtis:
            return []
        metas: list[TokenMetadata] = []
        for jti in jtis:
            payload = await self.redis.get(self._meta_key(jti))
            if not payload:
                continue
            metas.append(TokenMetadata.model_validate_json(payload))
        return metas

    async def get_metadata(self, jti: str) -> Optional[TokenMetadata]:
        payload = await self.redis.get(self._meta_key(jti))
        if not payload:
            return None
        return TokenMetadata.model_validate_json(payload)

    async def contains(self, user_id: uuid.UUID, jti: str) -> bool:
        return bool(await self.redis.sismember(self._user_key(user_id), jti))

    @staticmethod
    def _user_key(user_id: uuid.UUID) -> str:
        return f"user_tokens:{user_id}"

    @staticmethod
    def _meta_key(jti: str) -> str:
        return f"user_token:{jti}"
