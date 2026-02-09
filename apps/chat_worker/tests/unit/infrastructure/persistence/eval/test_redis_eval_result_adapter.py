"""RedisEvalResultAdapter Unit Tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from chat_worker.infrastructure.persistence.eval.redis_eval_result_adapter import (
    RedisEvalResultAdapter,
)


@pytest.mark.eval_unit
class TestRedisEvalResultAdapter:
    """RedisEvalResultAdapter 테스트."""

    def _make_adapter(self, redis: AsyncMock | None = None) -> RedisEvalResultAdapter:
        """테스트 팩토리."""
        return RedisEvalResultAdapter(redis=redis or AsyncMock())

    async def test_push_axis_scores_pipeline(self) -> None:
        """push_axis_scores가 LPUSH + LTRIM + EXPIRE pipeline 호출."""
        redis = MagicMock()
        pipe = MagicMock()
        pipe.execute = AsyncMock(return_value=[])
        redis.pipeline.return_value = pipe

        adapter = self._make_adapter(redis=redis)
        await adapter.push_axis_scores({"faithfulness": 4.0, "relevance": 3.5})

        # 2 axes × 3 ops (lpush + ltrim + expire) = 6 calls
        assert pipe.lpush.call_count == 2
        assert pipe.ltrim.call_count == 2
        assert pipe.expire.call_count == 2
        pipe.execute.assert_called_once()

    async def test_push_axis_scores_correct_keys(self) -> None:
        """push_axis_scores가 올바른 키를 사용하는지 검증."""
        redis = MagicMock()
        pipe = MagicMock()
        pipe.execute = AsyncMock(return_value=[])
        redis.pipeline.return_value = pipe

        adapter = self._make_adapter(redis=redis)
        await adapter.push_axis_scores({"safety": 5.0})

        pipe.lpush.assert_called_once_with("eval:axis_scores:safety", "5.0")
        pipe.ltrim.assert_called_once_with("eval:axis_scores:safety", 0, 99)

    async def test_get_recent_scores_returns_floats(self) -> None:
        """get_recent_scores가 float 리스트를 반환."""
        redis = AsyncMock()
        redis.lrange.return_value = ["4.0", "3.5", "5.0"]

        adapter = self._make_adapter(redis=redis)
        scores = await adapter.get_recent_scores("faithfulness", n=3)

        assert scores == [4.0, 3.5, 5.0]
        redis.lrange.assert_called_once_with("eval:axis_scores:faithfulness", 0, 2)

    async def test_get_recent_scores_empty(self) -> None:
        """데이터 없을 때 빈 리스트 반환."""
        redis = AsyncMock()
        redis.lrange.return_value = []

        adapter = self._make_adapter(redis=redis)
        scores = await adapter.get_recent_scores("relevance", n=10)

        assert scores == []

    async def test_get_recent_scores_none_returns_empty(self) -> None:
        """None 반환 시 빈 리스트."""
        redis = AsyncMock()
        redis.lrange.return_value = None

        adapter = self._make_adapter(redis=redis)
        scores = await adapter.get_recent_scores("completeness")

        assert scores == []

    async def test_increment_daily_cost(self) -> None:
        """increment_daily_cost가 INCRBYFLOAT 호출."""
        redis = MagicMock()
        pipe = MagicMock()
        pipe.execute = AsyncMock(return_value=[0.05, True])
        redis.pipeline.return_value = pipe

        adapter = self._make_adapter(redis=redis)
        total = await adapter.increment_daily_cost(0.05)

        assert total == 0.05
        pipe.incrbyfloat.assert_called_once()
        pipe.expire.assert_called_once()

    async def test_get_daily_cost_returns_float(self) -> None:
        """get_daily_cost가 float를 반환."""
        redis = AsyncMock()
        redis.get.return_value = "1.25"

        adapter = self._make_adapter(redis=redis)
        cost = await adapter.get_daily_cost()

        assert cost == 1.25

    async def test_get_daily_cost_returns_zero_when_missing(self) -> None:
        """키 없을 때 0.0 반환."""
        redis = AsyncMock()
        redis.get.return_value = None

        adapter = self._make_adapter(redis=redis)
        cost = await adapter.get_daily_cost()

        assert cost == 0.0
