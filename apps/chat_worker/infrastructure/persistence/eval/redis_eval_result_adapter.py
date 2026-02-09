"""Redis Eval Result Adapter - L2 Hot Storage.

Redis 기반 평가 결과 Hot Storage.
축별 최근 점수 캐시, 일일 비용 추적.

키 설계:
- eval:axis_scores:{axis} — LIST (최근 100건, FIFO)
- eval:daily_cost:{YYYY-MM-DD} — STRING (float, INCRBYFLOAT)

See: docs/plans/chat-eval-pipeline-plan.md §5.1 (Layered Memory)
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from redis.asyncio import Redis

logger = logging.getLogger(__name__)

_AXIS_SCORES_PREFIX = "eval:axis_scores"
_DAILY_COST_PREFIX = "eval:daily_cost"
_MAX_SCORES = 100  # 축별 최대 보관 점수 수
_SCORES_TTL = 7 * 86400  # 7일
_COST_TTL = 2 * 86400  # 2일


class RedisEvalResultAdapter:
    """Redis L2 Hot Storage for Eval Results.

    축별 최근 점수(CUSUM용)와 일일 비용 추적 제공.
    """

    def __init__(self, redis: "Redis") -> None:
        """초기화.

        Args:
            redis: Redis 클라이언트
        """
        self._redis = redis

    async def push_axis_scores(self, axis_scores: dict[str, float]) -> None:
        """축별 점수를 Redis LIST에 추가.

        LPUSH + LTRIM (100건) + EXPIRE 7d.

        Args:
            axis_scores: {axis_name: score} 매핑
        """
        pipe = self._redis.pipeline()
        for axis, score in axis_scores.items():
            key = f"{_AXIS_SCORES_PREFIX}:{axis}"
            pipe.lpush(key, str(score))
            pipe.ltrim(key, 0, _MAX_SCORES - 1)
            pipe.expire(key, _SCORES_TTL)
        await pipe.execute()

    async def get_recent_scores(self, axis: str, n: int = 10) -> list[float]:
        """특정 축의 최근 N개 점수 조회.

        Args:
            axis: 평가 축 이름
            n: 조회할 개수 (기본 10)

        Returns:
            최근 N개 점수 리스트 (최신순)
        """
        key = f"{_AXIS_SCORES_PREFIX}:{axis}"
        raw = await self._redis.lrange(key, 0, n - 1)
        return [float(v) for v in raw] if raw else []

    async def increment_daily_cost(self, cost_usd: float) -> float:
        """당일 평가 비용 누적.

        Args:
            cost_usd: 추가 비용 (USD)

        Returns:
            업데이트된 당일 누적 비용
        """
        key = self._make_cost_key()
        pipe = self._redis.pipeline()
        pipe.incrbyfloat(key, cost_usd)
        pipe.expire(key, _COST_TTL)
        results = await pipe.execute()
        return float(results[0])

    async def get_daily_cost(self) -> float:
        """당일 평가 비용 합계 조회.

        Returns:
            당일 누적 평가 비용 (USD)
        """
        key = self._make_cost_key()
        val = await self._redis.get(key)
        return float(val) if val else 0.0

    @staticmethod
    def _make_cost_key() -> str:
        """당일 날짜 기반 비용 키 생성."""
        today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
        return f"{_DAILY_COST_PREFIX}:{today}"


__all__ = ["RedisEvalResultAdapter"]
