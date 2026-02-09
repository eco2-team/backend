"""Redis Eval Counter - Global Request Counter.

Redis INCR 기반 전역 요청 카운터.
eval_cusum_check_interval 주기마다 Calibration Check 트리거 판단.

기존 stopgap(eval_retry_count 기반)을 대체하는 정확한 global counter.

키 설계:
- eval:request_count:{YYYY-MM-DD}
- TTL: 2일 (당일 + 이전 날짜 보존)

See: docs/plans/chat-eval-pipeline-plan.md B.3, #calibration-trigger
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from redis.asyncio import Redis

logger = logging.getLogger(__name__)

_KEY_PREFIX = "eval:request_count"
_TTL_SECONDS = 2 * 86400  # 2일


class RedisEvalCounter:
    """Redis INCR 기반 Global Eval Request Counter.

    increment_and_check()로 카운트 증가 + interval 판단을 원자적으로 수행.
    """

    def __init__(self, redis: "Redis", interval: int = 100) -> None:
        """초기화.

        Args:
            redis: Redis 클라이언트
            interval: Calibration 체크 주기 (N번째 요청마다)
        """
        self._redis = redis
        self._interval = interval

    @property
    def interval(self) -> int:
        """Calibration 체크 주기."""
        return self._interval

    async def increment_and_check(self) -> tuple[int, bool]:
        """카운트 증가 + Calibration 실행 여부 판단.

        Redis pipeline으로 INCR + EXPIRE를 원자적으로 수행.

        Returns:
            (count, should_calibrate) - 현재 카운트, Calibration 실행 여부
        """
        key = self._make_key()

        pipe = self._redis.pipeline()
        pipe.incr(key)
        pipe.expire(key, _TTL_SECONDS)
        results = await pipe.execute()

        count = int(results[0])
        should_calibrate = self._interval > 0 and count % self._interval == 0

        if should_calibrate:
            logger.info(
                "Calibration trigger: count=%d, interval=%d",
                count,
                self._interval,
            )

        return count, should_calibrate

    async def get_count(self) -> int:
        """현재 카운트 조회 (읽기 전용).

        Returns:
            현재 당일 요청 카운트
        """
        key = self._make_key()
        val = await self._redis.get(key)
        return int(val) if val else 0

    @staticmethod
    def _make_key() -> str:
        """당일 날짜 기반 키 생성."""
        today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
        return f"{_KEY_PREFIX}:{today}"


__all__ = ["RedisEvalCounter"]
