"""Composite Eval Gateway - Redis + PostgreSQL Layered Memory.

Redis (L2 Hot) + PostgreSQL (L3 Cold) 동시 저장/조회.
PG pool=None → Redis-only 모드 (로컬 개발).

CQS(Command-Query Separation) 패턴:
- CompositeEvalCommandGateway: save_result, save_drift_log
- CompositeEvalQueryGateway: get_recent_scores, get_daily_cost, get_intent_distribution

See: docs/plans/chat-eval-pipeline-plan.md §5.1
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from chat_worker.application.dto.eval_result import EvalResult
    from chat_worker.infrastructure.persistence.eval.postgres_eval_result_adapter import (
        PostgresEvalResultAdapter,
    )
    from chat_worker.infrastructure.persistence.eval.redis_eval_result_adapter import (
        RedisEvalResultAdapter,
    )

logger = logging.getLogger(__name__)


class CompositeEvalCommandGateway:
    """Eval 결과 저장 Gateway (Redis + PG 동시 저장).

    EvalResultCommandGateway Protocol 구현.
    PG 실패 시 non-blocking (Redis는 항상 저장).
    pg_adapter=None → Redis-only 모드.
    """

    def __init__(
        self,
        redis_adapter: "RedisEvalResultAdapter",
        pg_adapter: "PostgresEvalResultAdapter | None" = None,
    ) -> None:
        self._redis = redis_adapter
        self._pg = pg_adapter

    async def save_result(self, eval_result: "EvalResult") -> None:
        """평가 결과 저장 (Redis + PG).

        Redis: 축별 점수 + 일일 비용 (hot path)
        PG: 전체 결과 INSERT (cold storage, non-blocking)

        Args:
            eval_result: 평가 결과 DTO
        """
        result_dict = eval_result.to_dict()

        # Redis: 축별 점수 캐시
        axis_scores = result_dict.get("axis_scores", {})
        if axis_scores:
            flat_scores = {}
            for axis, score_data in axis_scores.items():
                if isinstance(score_data, dict) and "score" in score_data:
                    flat_scores[axis] = float(score_data["score"])
            if flat_scores:
                await self._redis.push_axis_scores(flat_scores)

        # Redis: 일일 비용 누적
        cost = result_dict.get("eval_cost_usd")
        if cost is not None and cost > 0:
            await self._redis.increment_daily_cost(cost)

        # PG: 전체 결과 저장 (non-blocking)
        if self._pg is not None:
            try:
                await self._pg.save_result(result_dict)
            except Exception as e:
                logger.warning(
                    "PG save_result failed (non-blocking): %s",
                    e,
                    exc_info=True,
                )

    async def save_drift_log(self, drift_entry: dict[str, Any]) -> None:
        """Calibration Drift 로그 저장 (PG only).

        Args:
            drift_entry: drift 탐지 정보
        """
        if self._pg is not None:
            try:
                await self._pg.save_drift_log(drift_entry)
            except Exception as e:
                logger.warning(
                    "PG save_drift_log failed (non-blocking): %s",
                    e,
                    exc_info=True,
                )
        else:
            logger.debug(
                "save_drift_log skipped (PG not configured)",
                extra={"drift_entry": drift_entry},
            )


class CompositeEvalQueryGateway:
    """Eval 결과 조회 Gateway (Redis-first, PG fallback).

    EvalResultQueryGateway Protocol 구현.
    Redis에서 먼저 조회, miss 시 PG fallback.
    pg_adapter=None → Redis-only 모드.
    """

    def __init__(
        self,
        redis_adapter: "RedisEvalResultAdapter",
        pg_adapter: "PostgresEvalResultAdapter | None" = None,
    ) -> None:
        self._redis = redis_adapter
        self._pg = pg_adapter

    async def get_recent_scores(self, axis: str, n: int = 10) -> list[float]:
        """특정 축의 최근 N개 점수 조회.

        Redis-first, PG fallback.

        Args:
            axis: 평가 축 이름
            n: 조회할 개수

        Returns:
            최근 N개 점수 리스트
        """
        scores = await self._redis.get_recent_scores(axis, n)
        if scores:
            return scores

        # PG fallback
        if self._pg is not None:
            try:
                return await self._pg.get_recent_scores(axis, n)
            except Exception as e:
                logger.warning("PG get_recent_scores fallback failed: %s", e)

        return []

    async def get_daily_cost(self) -> float:
        """당일 평가 비용 합계 (Redis only).

        Returns:
            당일 누적 평가 비용 (USD)
        """
        return await self._redis.get_daily_cost()

    async def get_intent_distribution(self, days: int = 7) -> dict[str, float]:
        """최근 N일간 Intent별 트래픽 비율.

        PG only (Redis는 집계 데이터 미보관).

        Args:
            days: 조회 기간

        Returns:
            intent -> 비율 매핑
        """
        if self._pg is not None:
            try:
                return await self._pg.get_intent_distribution(days)
            except Exception as e:
                logger.warning("PG get_intent_distribution failed: %s", e)

        return {}


__all__ = [
    "CompositeEvalCommandGateway",
    "CompositeEvalQueryGateway",
]
