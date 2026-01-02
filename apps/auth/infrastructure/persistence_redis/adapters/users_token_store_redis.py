"""Redis Users Token Store.

UsersTokenStore 포트의 구현체입니다.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from uuid import UUID

from apps.auth.application.token.ports import TokenMetadata
from apps.auth.infrastructure.persistence_redis.constants import (
    TOKEN_META_KEY_PREFIX,
    USER_TOKENS_KEY_PREFIX,
)

if TYPE_CHECKING:
    import redis.asyncio as aioredis


class RedisUsersTokenStore:
    """Redis 기반 사용자 토큰 저장소.

    UsersTokenStore 구현체.
    """

    def __init__(self, redis: "aioredis.Redis") -> None:
        self._redis = redis

    async def register(
        self,
        *,
        user_id: UUID,
        jti: str,
        issued_at: int,
        expires_at: int,
        device_id: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        """토큰 등록."""
        import time

        user_key = f"{USER_TOKENS_KEY_PREFIX}{user_id}"
        meta_key = f"{TOKEN_META_KEY_PREFIX}{jti}"
        ttl = max(expires_at - int(time.time()), 1)

        # 사용자별 토큰 Set에 추가
        await self._redis.sadd(user_key, jti)
        await self._redis.expire(user_key, ttl)

        # 토큰 메타데이터 저장
        meta = json.dumps(
            {
                "device_id": device_id,
                "user_agent": user_agent,
                "issued_at": issued_at,
            }
        )
        await self._redis.setex(meta_key, ttl, meta)

    async def contains(self, user_id: UUID, jti: str) -> bool:
        """토큰 존재 여부 확인."""
        user_key = f"{USER_TOKENS_KEY_PREFIX}{user_id}"
        return await self._redis.sismember(user_key, jti)

    async def remove(self, user_id: UUID, jti: str) -> None:
        """토큰 제거."""
        user_key = f"{USER_TOKENS_KEY_PREFIX}{user_id}"
        meta_key = f"{TOKEN_META_KEY_PREFIX}{jti}"
        await self._redis.srem(user_key, jti)
        await self._redis.delete(meta_key)

    async def get_metadata(self, jti: str) -> TokenMetadata | None:
        """토큰 메타데이터 조회."""
        meta_key = f"{TOKEN_META_KEY_PREFIX}{jti}"
        value = await self._redis.get(meta_key)
        if not value:
            return None

        data = json.loads(value)
        return TokenMetadata(
            device_id=data.get("device_id"),
            user_agent=data.get("user_agent"),
        )
