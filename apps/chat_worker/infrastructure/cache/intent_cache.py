"""Intent Cache - 분류 결과 Redis 캐싱.

동일한 메시지에 대해 Intent 분류 결과를 캐싱합니다.
LLM 호출 비용 절감 및 응답 시간 단축.

Cache-Aside 패턴:
1. 캐시 조회
2. Cache Hit → 즉시 반환
3. Cache Miss → LLM 호출 → 결과 캐싱

키 설계:
- chat:intent:{message_hash}
- TTL: 1시간 (동일 메시지 반복 질문 대응)
"""

from __future__ import annotations

import hashlib
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from redis.asyncio import Redis

logger = logging.getLogger(__name__)

CACHE_KEY_PREFIX = "chat:intent"
DEFAULT_TTL = 3600  # 1시간


class IntentCache:
    """Intent 분류 결과 캐시.

    메시지 해시를 키로 사용하여 Intent 분류 결과를 캐싱합니다.
    """

    def __init__(
        self,
        redis: "Redis",
        ttl: int = DEFAULT_TTL,
        key_prefix: str = CACHE_KEY_PREFIX,
    ):
        """초기화.

        Args:
            redis: Redis 클라이언트
            ttl: 캐시 TTL 초 (기본 1시간)
            key_prefix: 캐시 키 프리픽스
        """
        self._redis = redis
        self._ttl = ttl
        self._key_prefix = key_prefix

    def _make_key(self, message: str) -> str:
        """메시지 해시로 캐시 키 생성.

        메시지 정규화:
        - 소문자 변환
        - 앞뒤 공백 제거
        - SHA256 해시
        """
        normalized = message.strip().lower()
        message_hash = hashlib.sha256(normalized.encode()).hexdigest()[:16]
        return f"{self._key_prefix}:{message_hash}"

    async def get(self, message: str) -> str | None:
        """캐시된 Intent 조회.

        Args:
            message: 사용자 메시지

        Returns:
            캐시된 Intent (없으면 None)
        """
        key = self._make_key(message)

        try:
            cached = await self._redis.get(key)
            if cached:
                logger.debug(
                    "intent_cache_hit",
                    extra={"key": key, "intent": cached},
                )
                return cached
        except Exception as e:
            logger.warning(
                "intent_cache_get_failed",
                extra={"key": key, "error": str(e)},
            )

        return None

    async def set(self, message: str, intent: str) -> bool:
        """Intent 결과 캐싱.

        Args:
            message: 사용자 메시지
            intent: 분류된 Intent

        Returns:
            캐싱 성공 여부
        """
        key = self._make_key(message)

        try:
            await self._redis.setex(key, self._ttl, intent)
            logger.debug(
                "intent_cache_set",
                extra={"key": key, "intent": intent, "ttl": self._ttl},
            )
            return True
        except Exception as e:
            logger.warning(
                "intent_cache_set_failed",
                extra={"key": key, "error": str(e)},
            )
            return False

    async def get_with_metadata(self, message: str) -> dict | None:
        """메타데이터 포함 캐시 조회.

        Args:
            message: 사용자 메시지

        Returns:
            {"intent": str, "cached_at": str, "ttl_remaining": int} or None
        """
        key = self._make_key(message)

        try:
            # MULTI: GET + TTL
            pipe = self._redis.pipeline()
            pipe.get(key)
            pipe.ttl(key)
            results = await pipe.execute()

            intent, ttl_remaining = results
            if intent:
                return {
                    "intent": intent,
                    "ttl_remaining": ttl_remaining,
                    "cache_key": key,
                }
        except Exception as e:
            logger.warning(
                "intent_cache_get_metadata_failed",
                extra={"key": key, "error": str(e)},
            )

        return None

    async def invalidate(self, message: str) -> bool:
        """캐시 무효화.

        Args:
            message: 사용자 메시지

        Returns:
            삭제 성공 여부
        """
        key = self._make_key(message)

        try:
            deleted = await self._redis.unlink(key)
            logger.debug(
                "intent_cache_invalidated",
                extra={"key": key, "deleted": deleted},
            )
            return deleted > 0
        except Exception as e:
            logger.warning(
                "intent_cache_invalidate_failed",
                extra={"key": key, "error": str(e)},
            )
            return False

    async def clear_all(self) -> int:
        """모든 Intent 캐시 삭제.

        Returns:
            삭제된 키 수
        """
        pattern = f"{self._key_prefix}:*"

        try:
            keys = []
            async for key in self._redis.scan_iter(match=pattern):
                keys.append(key)

            if keys:
                deleted = await self._redis.unlink(*keys)
                logger.info(
                    "intent_cache_cleared",
                    extra={"deleted_count": deleted},
                )
                return deleted
            return 0
        except Exception as e:
            logger.warning(
                "intent_cache_clear_failed",
                extra={"error": str(e)},
            )
            return 0
