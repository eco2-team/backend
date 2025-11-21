from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Optional
import secrets
import base64
import hashlib

from fastapi import Depends
from redis.asyncio import Redis

from app.core.config import get_settings


def now_utc() -> datetime:
    return datetime.utcnow()


def generate_state() -> str:
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).decode().rstrip("=")


def generate_code_verifier() -> str:
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).decode().rstrip("=")


def generate_code_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")


def compute_ttl_seconds(expires_at: datetime) -> int:
    delta = expires_at - now_utc()
    return int(delta.total_seconds())


async def get_oauth_state_redis() -> Redis:
    """OAuth state용 Redis 클라이언트를 반환합니다."""
    settings = get_settings()
    return Redis.from_url(settings.redis_oauth_state_url, decode_responses=True)


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
