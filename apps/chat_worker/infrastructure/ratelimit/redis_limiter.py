"""Redis Rate Limiter - Sliding Window 기반 요청 제한.

알고리즘: Sliding Window Counter
- 현재 윈도우와 이전 윈도우의 가중 평균 사용
- 정확도와 메모리 효율성의 균형

키 설계:
- chat:ratelimit:{user_id}:{window_id}
- window_id = timestamp // window_size

제한 정책:
- 분당 요청 수 제한 (기본 60/분)
- 사용자별 독립 제한
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from redis.asyncio import Redis

logger = logging.getLogger(__name__)

RATE_LIMIT_PREFIX = "chat:ratelimit"
DEFAULT_LIMIT = 60  # 분당 60 요청
DEFAULT_WINDOW = 60  # 60초 윈도우


class RateLimitExceeded(Exception):
    """Rate Limit 초과 예외."""

    def __init__(
        self,
        user_id: str,
        limit: int,
        remaining: int,
        reset_after: int,
    ):
        self.user_id = user_id
        self.limit = limit
        self.remaining = remaining
        self.reset_after = reset_after
        super().__init__(
            f"Rate limit exceeded for {user_id}: " f"{limit}/min, reset in {reset_after}s"
        )


@dataclass
class RateLimitInfo:
    """Rate Limit 정보."""

    user_id: str
    limit: int
    remaining: int
    reset_after: int
    allowed: bool


class RateLimiter:
    """Redis 기반 Rate Limiter.

    Sliding Window Counter 알고리즘 사용.
    """

    def __init__(
        self,
        redis: "Redis",
        limit: int = DEFAULT_LIMIT,
        window: int = DEFAULT_WINDOW,
        key_prefix: str = RATE_LIMIT_PREFIX,
    ):
        """초기화.

        Args:
            redis: Redis 클라이언트
            limit: 윈도우당 최대 요청 수 (기본 60)
            window: 윈도우 크기 초 (기본 60)
            key_prefix: 키 프리픽스
        """
        self._redis = redis
        self._limit = limit
        self._window = window
        self._key_prefix = key_prefix

    def _get_window_id(self, timestamp: float | None = None) -> int:
        """현재 윈도우 ID 계산."""
        ts = timestamp or time.time()
        return int(ts // self._window)

    def _make_key(self, user_id: str, window_id: int) -> str:
        """Rate Limit 키 생성."""
        return f"{self._key_prefix}:{user_id}:{window_id}"

    async def check(self, user_id: str) -> RateLimitInfo:
        """Rate Limit 확인 (요청 카운트 증가 없음).

        Args:
            user_id: 사용자 ID

        Returns:
            RateLimitInfo 객체
        """
        now = time.time()
        current_window = self._get_window_id(now)
        prev_window = current_window - 1

        current_key = self._make_key(user_id, current_window)
        prev_key = self._make_key(user_id, prev_window)

        # 현재/이전 윈도우 카운트 조회
        pipe = self._redis.pipeline()
        pipe.get(current_key)
        pipe.get(prev_key)
        results = await pipe.execute()

        current_count = int(results[0] or 0)
        prev_count = int(results[1] or 0)

        # Sliding Window 가중치 계산
        elapsed_in_window = now - (current_window * self._window)
        weight = 1 - (elapsed_in_window / self._window)
        weighted_count = current_count + (prev_count * weight)

        remaining = max(0, self._limit - int(weighted_count))
        reset_after = self._window - int(elapsed_in_window)
        allowed = remaining > 0

        return RateLimitInfo(
            user_id=user_id,
            limit=self._limit,
            remaining=remaining,
            reset_after=reset_after,
            allowed=allowed,
        )

    async def acquire(self, user_id: str) -> RateLimitInfo:
        """Rate Limit 획득 (요청 카운트 증가).

        Args:
            user_id: 사용자 ID

        Returns:
            RateLimitInfo 객체

        Raises:
            RateLimitExceeded: 제한 초과 시
        """
        info = await self.check(user_id)

        if not info.allowed:
            raise RateLimitExceeded(
                user_id=user_id,
                limit=info.limit,
                remaining=info.remaining,
                reset_after=info.reset_after,
            )

        # 카운트 증가
        now = time.time()
        current_window = self._get_window_id(now)
        key = self._make_key(user_id, current_window)

        pipe = self._redis.pipeline()
        pipe.incr(key)
        pipe.expire(key, self._window * 2)  # 2 윈도우 TTL
        await pipe.execute()

        # 업데이트된 정보 반환
        return RateLimitInfo(
            user_id=user_id,
            limit=self._limit,
            remaining=info.remaining - 1,
            reset_after=info.reset_after,
            allowed=True,
        )

    async def reset(self, user_id: str) -> bool:
        """사용자 Rate Limit 초기화.

        Args:
            user_id: 사용자 ID

        Returns:
            성공 여부
        """
        pattern = f"{self._key_prefix}:{user_id}:*"

        try:
            keys = []
            async for key in self._redis.scan_iter(match=pattern):
                keys.append(key)

            if keys:
                await self._redis.delete(*keys)
                logger.info(
                    "rate_limit_reset",
                    extra={"user_id": user_id, "keys_deleted": len(keys)},
                )
            return True
        except Exception as e:
            logger.warning(
                "rate_limit_reset_failed",
                extra={"user_id": user_id, "error": str(e)},
            )
            return False

    async def get_headers(self, user_id: str) -> dict[str, str]:
        """Rate Limit HTTP 헤더 생성.

        RFC 6585 표준 헤더:
        - X-RateLimit-Limit
        - X-RateLimit-Remaining
        - X-RateLimit-Reset
        """
        info = await self.check(user_id)

        return {
            "X-RateLimit-Limit": str(info.limit),
            "X-RateLimit-Remaining": str(info.remaining),
            "X-RateLimit-Reset": str(info.reset_after),
        }
