"""Redis Cache Adapter - CachePort 구현.

Infrastructure Layer에서 CachePort를 구현합니다.
Application Layer는 Redis를 직접 알지 않고 CachePort만 사용.

특징:
- 비동기 Redis 클라이언트 (redis.asyncio)
- TTL 지원
- 에러 시 graceful degradation (로그만 남기고 None/False 반환)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from chat_worker.application.ports.cache import CachePort

if TYPE_CHECKING:
    from redis.asyncio import Redis

logger = logging.getLogger(__name__)


class RedisCacheAdapter(CachePort):
    """Redis 캐시 어댑터.

    CachePort를 Redis로 구현합니다.
    Application Layer에서는 CachePort 타입으로만 주입받습니다.

    사용 예시:
        cache = RedisCacheAdapter(redis_client)
        await cache.set("key", "value", ttl=3600)
        value = await cache.get("key")
    """

    def __init__(self, redis: "Redis", key_prefix: str = ""):
        """초기화.

        Args:
            redis: Redis 클라이언트 인스턴스
            key_prefix: 모든 키에 붙일 프리픽스 (예: "chat:cache:")
        """
        self._redis = redis
        self._key_prefix = key_prefix

    def _make_key(self, key: str) -> str:
        """프리픽스를 붙인 키 생성."""
        if self._key_prefix:
            return f"{self._key_prefix}{key}"
        return key

    async def get(self, key: str) -> str | None:
        """캐시 조회."""
        full_key = self._make_key(key)
        try:
            value = await self._redis.get(full_key)
            if value is not None:
                logger.debug("cache_hit", extra={"key": full_key})
            return value
        except Exception as e:
            logger.warning(
                "cache_get_failed",
                extra={"key": full_key, "error": str(e)},
            )
            return None

    async def set(self, key: str, value: str, ttl: int | None = None) -> bool:
        """캐시 저장."""
        full_key = self._make_key(key)
        try:
            if ttl:
                await self._redis.setex(full_key, ttl, value)
            else:
                await self._redis.set(full_key, value)
            logger.debug(
                "cache_set",
                extra={"key": full_key, "ttl": ttl},
            )
            return True
        except Exception as e:
            logger.warning(
                "cache_set_failed",
                extra={"key": full_key, "error": str(e)},
            )
            return False

    async def delete(self, key: str) -> bool:
        """캐시 삭제."""
        full_key = self._make_key(key)
        try:
            deleted = await self._redis.delete(full_key)
            logger.debug(
                "cache_delete",
                extra={"key": full_key, "deleted": deleted > 0},
            )
            return deleted > 0
        except Exception as e:
            logger.warning(
                "cache_delete_failed",
                extra={"key": full_key, "error": str(e)},
            )
            return False

    async def exists(self, key: str) -> bool:
        """캐시 존재 여부 확인."""
        full_key = self._make_key(key)
        try:
            return await self._redis.exists(full_key) > 0
        except Exception as e:
            logger.warning(
                "cache_exists_failed",
                extra={"key": full_key, "error": str(e)},
            )
            return False

    # === 추가 유틸리티 메서드 ===

    async def ttl(self, key: str) -> int:
        """남은 TTL 조회.

        Args:
            key: 캐시 키

        Returns:
            남은 TTL 초 (-1: 무기한, -2: 키 없음)
        """
        full_key = self._make_key(key)
        try:
            return await self._redis.ttl(full_key)
        except Exception as e:
            logger.warning(
                "cache_ttl_failed",
                extra={"key": full_key, "error": str(e)},
            )
            return -2

    async def expire(self, key: str, ttl: int) -> bool:
        """TTL 갱신.

        Args:
            key: 캐시 키
            ttl: 새 TTL 초

        Returns:
            갱신 성공 여부
        """
        full_key = self._make_key(key)
        try:
            return await self._redis.expire(full_key, ttl)
        except Exception as e:
            logger.warning(
                "cache_expire_failed",
                extra={"key": full_key, "error": str(e)},
            )
            return False
