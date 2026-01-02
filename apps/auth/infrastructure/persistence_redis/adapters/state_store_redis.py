"""Redis State Store.

StateStore 포트의 구현체입니다.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from apps.auth.application.oauth.ports import OAuthState
from apps.auth.infrastructure.persistence_redis.constants import STATE_KEY_PREFIX

if TYPE_CHECKING:
    import redis.asyncio as aioredis


class RedisStateStore:
    """Redis 기반 OAuth 상태 저장소.

    StateStore 구현체.
    """

    def __init__(self, redis: "aioredis.Redis") -> None:
        self._redis = redis

    async def save(self, state: str, data: OAuthState, ttl_seconds: int = 600) -> None:
        """상태 저장."""
        key = f"{STATE_KEY_PREFIX}{state}"
        value = json.dumps(
            {
                "provider": data.provider,
                "redirect_uri": data.redirect_uri,
                "code_verifier": data.code_verifier,
                "device_id": data.device_id,
                "frontend_origin": data.frontend_origin,
            }
        )
        await self._redis.setex(key, ttl_seconds, value)

    async def consume(self, state: str) -> OAuthState | None:
        """상태 조회 및 삭제."""
        key = f"{STATE_KEY_PREFIX}{state}"
        value = await self._redis.get(key)
        if not value:
            return None

        await self._redis.delete(key)
        data = json.loads(value)
        return OAuthState(
            provider=data["provider"],
            redirect_uri=data.get("redirect_uri"),
            code_verifier=data.get("code_verifier"),
            device_id=data.get("device_id"),
            frontend_origin=data.get("frontend_origin"),
        )
