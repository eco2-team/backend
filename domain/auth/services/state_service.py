from __future__ import annotations

import json
from datetime import timedelta
from typing import Optional

from fastapi import Depends
from redis.asyncio import Redis

from domain.auth.core.config import get_settings
from domain.auth.core.redis import get_oauth_state_redis
from domain.auth.core.security import (
    compute_ttl_seconds,
    generate_code_challenge,
    generate_code_verifier,
    generate_state,
    now_utc,
)


class OAuthStateData(dict): ...


class OAuthStateStore:
    def __init__(self, redis: Redis = Depends(get_oauth_state_redis)):
        self.redis = redis
        self.settings = get_settings()

    async def create_state(
        self,
        *,
        provider: str,
        redirect_uri: str,
        scope: Optional[str],
        device_id: Optional[str],
    ) -> tuple[str, str, str, int]:
        state = generate_state()
        code_verifier = generate_code_verifier()
        code_challenge = generate_code_challenge(code_verifier)
        expires_at = now_utc() + timedelta(seconds=self.settings.oauth_state_ttl_seconds)

        payload = {
            "provider": provider,
            "redirect_uri": redirect_uri,
            "scope": scope,
            "device_id": device_id,
            "code_verifier": code_verifier,
            "code_challenge": code_challenge,
            "expires_at": expires_at.isoformat(),
        }
        ttl = max(compute_ttl_seconds(expires_at), 1)
        await self.redis.setex(self._key(state), ttl, json.dumps(payload))
        return state, code_verifier, code_challenge, int(expires_at.timestamp())

    async def consume_state(self, state: str) -> Optional[OAuthStateData]:
        key = self._key(state)
        payload = await self.redis.get(key)
        if payload is None:
            return None
        await self.redis.delete(key)
        return OAuthStateData(json.loads(payload))

    @staticmethod
    def _key(state: str) -> str:
        return f"oauth:state:{state}"
