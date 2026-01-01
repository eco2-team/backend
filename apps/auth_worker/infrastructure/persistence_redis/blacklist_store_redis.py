"""Redis Blacklist Store.

Redis 기반 블랙리스트 저장소 구현체입니다.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

# ext-authz와 동일한 키 prefix 사용
BLACKLIST_KEY_PREFIX = "blacklist:"


class RedisBlacklistStore:
    """Redis 기반 블랙리스트 저장소.

    BlacklistStore 인터페이스 구현체입니다.
    ext-authz와 동일한 키 형식을 사용합니다.
    """

    def __init__(self, redis: "aioredis.Redis") -> None:
        """Initialize.

        Args:
            redis: Redis 클라이언트
        """
        self._redis = redis

    async def add(
        self,
        jti: str,
        expires_at: datetime,
        *,
        user_id: str | None = None,
        reason: str | None = None,
    ) -> None:
        """토큰을 블랙리스트에 추가.

        Args:
            jti: JWT Token ID
            expires_at: 토큰 만료 시간 (TTL 계산용)
            user_id: 사용자 ID (로깅용)
            reason: 블랙리스트 사유
        """
        key = f"{BLACKLIST_KEY_PREFIX}{jti}"

        # TTL 계산 (토큰 만료 시간까지)
        now = datetime.now(timezone.utc)
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)

        ttl = int((expires_at - now).total_seconds())
        if ttl <= 0:
            logger.debug(
                "Token already expired, skipping blacklist",
                extra={"jti": jti[:8]},
            )
            return

        # 메타데이터 저장 (ext-authz 호환)
        data = {
            "user_id": user_id,
            "reason": reason or "logout",
            "blacklisted_at": now.isoformat(),
            "expires_at": expires_at.isoformat(),
        }

        await self._redis.setex(key, ttl, json.dumps(data))
        logger.debug(
            "Token added to blacklist",
            extra={"jti": jti[:8], "ttl": ttl},
        )

    async def contains(self, jti: str) -> bool:
        """토큰이 블랙리스트에 있는지 확인.

        Args:
            jti: JWT Token ID

        Returns:
            블랙리스트에 있으면 True
        """
        key = f"{BLACKLIST_KEY_PREFIX}{jti}"
        return await self._redis.exists(key) > 0

    async def remove(self, jti: str) -> None:
        """토큰을 블랙리스트에서 제거.

        Args:
            jti: JWT Token ID
        """
        key = f"{BLACKLIST_KEY_PREFIX}{jti}"
        await self._redis.delete(key)
        logger.debug(
            "Token removed from blacklist",
            extra={"jti": jti[:8]},
        )
