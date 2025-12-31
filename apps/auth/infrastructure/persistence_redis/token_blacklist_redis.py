"""Redis Token Blacklist.

TokenBlacklist 포트의 구현체입니다.

Note:
    블랙리스트 추가는 BlacklistEventPublisher를 통해 이벤트로 발행됩니다.
    auth_worker가 이벤트를 소비하여 Redis에 저장합니다.
    이 클래스는 읽기(조회) 전용입니다.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import redis.asyncio as aioredis

# auth_worker와 동일한 키 prefix 사용
BLACKLIST_KEY_PREFIX = "blacklist:"


class RedisTokenBlacklist:
    """Redis 기반 토큰 블랙리스트 (읽기 전용).

    TokenBlacklist 구현체.
    블랙리스트 추가는 BlacklistEventPublisher를 사용하세요.
    """

    def __init__(self, redis: "aioredis.Redis") -> None:
        self._redis = redis

    async def contains(self, jti: str) -> bool:
        """토큰이 블랙리스트에 있는지 확인."""
        key = f"{BLACKLIST_KEY_PREFIX}{jti}"
        return await self._redis.exists(key) > 0
