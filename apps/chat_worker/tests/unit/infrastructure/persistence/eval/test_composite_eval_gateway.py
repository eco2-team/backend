"""CompositeEvalGateway Unit Tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from chat_worker.infrastructure.persistence.eval.composite_eval_gateway import (
    CompositeEvalCommandGateway,
    CompositeEvalQueryGateway,
)


def _make_eval_result_mock(
    axis_scores: dict | None = None,
    cost: float | None = None,
) -> MagicMock:
    """EvalResult mock 팩토리."""
    result = MagicMock()
    result.to_dict.return_value = {
        "grade": "A",
        "continuous_score": 82.5,
        "axis_scores": axis_scores
        or {
            "faithfulness": {"score": 4, "reasoning": "good"},
            "relevance": {"score": 5, "reasoning": "excellent"},
        },
        "eval_cost_usd": cost,
        "model_version": "gpt-4o-mini",
        "prompt_version": "v1.0",
        "eval_duration_ms": 150,
        "calibration_status": "STABLE",
        "code_grader_result": {"overall_score": 75.0},
        "llm_grader_result": None,
        "metadata": {"intent": "waste", "eval_mode": "async"},
    }
    return result


@pytest.mark.eval_unit
class TestCompositeEvalCommandGateway:
    """CompositeEvalCommandGateway 테스트."""

    async def test_save_result_redis_and_pg(self) -> None:
        """Redis + PG 동시 저장 검증."""
        redis_adapter = AsyncMock()
        pg_adapter = AsyncMock()

        gw = CompositeEvalCommandGateway(
            redis_adapter=redis_adapter,
            pg_adapter=pg_adapter,
        )
        eval_result = _make_eval_result_mock(cost=0.05)
        await gw.save_result(eval_result)

        redis_adapter.push_axis_scores.assert_called_once()
        redis_adapter.increment_daily_cost.assert_called_once_with(0.05)
        pg_adapter.save_result.assert_called_once()

    async def test_save_result_redis_only_when_pg_none(self) -> None:
        """PG=None → Redis-only 저장."""
        redis_adapter = AsyncMock()

        gw = CompositeEvalCommandGateway(
            redis_adapter=redis_adapter,
            pg_adapter=None,
        )
        eval_result = _make_eval_result_mock(cost=0.03)
        await gw.save_result(eval_result)

        redis_adapter.push_axis_scores.assert_called_once()
        redis_adapter.increment_daily_cost.assert_called_once_with(0.03)

    async def test_save_result_pg_failure_non_blocking(self) -> None:
        """PG 실패 시 non-blocking (Redis는 성공)."""
        redis_adapter = AsyncMock()
        pg_adapter = AsyncMock()
        pg_adapter.save_result.side_effect = Exception("PG connection failed")

        gw = CompositeEvalCommandGateway(
            redis_adapter=redis_adapter,
            pg_adapter=pg_adapter,
        )
        eval_result = _make_eval_result_mock()
        # PG 실패해도 예외 발생 안 함
        await gw.save_result(eval_result)

        redis_adapter.push_axis_scores.assert_called_once()

    async def test_save_result_no_cost_skips_increment(self) -> None:
        """eval_cost_usd가 None이면 increment 스킵."""
        redis_adapter = AsyncMock()

        gw = CompositeEvalCommandGateway(
            redis_adapter=redis_adapter,
            pg_adapter=None,
        )
        eval_result = _make_eval_result_mock(cost=None)
        await gw.save_result(eval_result)

        redis_adapter.increment_daily_cost.assert_not_called()

    async def test_save_result_zero_cost_skips_increment(self) -> None:
        """eval_cost_usd=0이면 increment 스킵."""
        redis_adapter = AsyncMock()

        gw = CompositeEvalCommandGateway(
            redis_adapter=redis_adapter,
            pg_adapter=None,
        )
        eval_result = _make_eval_result_mock(cost=0.0)
        await gw.save_result(eval_result)

        redis_adapter.increment_daily_cost.assert_not_called()

    async def test_save_drift_log_pg(self) -> None:
        """save_drift_log PG 저장."""
        redis_adapter = AsyncMock()
        pg_adapter = AsyncMock()

        gw = CompositeEvalCommandGateway(
            redis_adapter=redis_adapter,
            pg_adapter=pg_adapter,
        )
        drift = {"axis": "faithfulness", "severity": "WARNING"}
        await gw.save_drift_log(drift)

        pg_adapter.save_drift_log.assert_called_once_with(drift)

    async def test_save_drift_log_no_pg_graceful(self) -> None:
        """PG=None일 때 save_drift_log 무시."""
        redis_adapter = AsyncMock()

        gw = CompositeEvalCommandGateway(
            redis_adapter=redis_adapter,
            pg_adapter=None,
        )
        # 예외 없이 실행
        await gw.save_drift_log({"axis": "relevance"})


@pytest.mark.eval_unit
class TestCompositeEvalQueryGateway:
    """CompositeEvalQueryGateway 테스트."""

    async def test_get_recent_scores_redis_hit(self) -> None:
        """Redis에 데이터 있으면 Redis 반환."""
        redis_adapter = AsyncMock()
        redis_adapter.get_recent_scores.return_value = [4.0, 3.5, 5.0]
        pg_adapter = AsyncMock()

        gw = CompositeEvalQueryGateway(
            redis_adapter=redis_adapter,
            pg_adapter=pg_adapter,
        )
        scores = await gw.get_recent_scores("faithfulness", n=3)

        assert scores == [4.0, 3.5, 5.0]
        pg_adapter.get_recent_scores.assert_not_called()

    async def test_get_recent_scores_redis_miss_pg_fallback(self) -> None:
        """Redis miss → PG fallback."""
        redis_adapter = AsyncMock()
        redis_adapter.get_recent_scores.return_value = []
        pg_adapter = AsyncMock()
        pg_adapter.get_recent_scores.return_value = [3.0, 4.0]

        gw = CompositeEvalQueryGateway(
            redis_adapter=redis_adapter,
            pg_adapter=pg_adapter,
        )
        scores = await gw.get_recent_scores("relevance", n=5)

        assert scores == [3.0, 4.0]

    async def test_get_recent_scores_both_empty(self) -> None:
        """Redis + PG 모두 비어있으면 빈 리스트."""
        redis_adapter = AsyncMock()
        redis_adapter.get_recent_scores.return_value = []
        pg_adapter = AsyncMock()
        pg_adapter.get_recent_scores.return_value = []

        gw = CompositeEvalQueryGateway(
            redis_adapter=redis_adapter,
            pg_adapter=pg_adapter,
        )
        scores = await gw.get_recent_scores("safety", n=10)

        assert scores == []

    async def test_get_recent_scores_no_pg_returns_empty(self) -> None:
        """PG=None, Redis miss → 빈 리스트."""
        redis_adapter = AsyncMock()
        redis_adapter.get_recent_scores.return_value = []

        gw = CompositeEvalQueryGateway(
            redis_adapter=redis_adapter,
            pg_adapter=None,
        )
        scores = await gw.get_recent_scores("communication", n=5)

        assert scores == []

    async def test_get_daily_cost(self) -> None:
        """get_daily_cost Redis 호출."""
        redis_adapter = AsyncMock()
        redis_adapter.get_daily_cost.return_value = 2.50

        gw = CompositeEvalQueryGateway(
            redis_adapter=redis_adapter,
            pg_adapter=None,
        )
        cost = await gw.get_daily_cost()

        assert cost == 2.50

    async def test_get_intent_distribution_pg(self) -> None:
        """get_intent_distribution PG 조회."""
        redis_adapter = AsyncMock()
        pg_adapter = AsyncMock()
        pg_adapter.get_intent_distribution.return_value = {"waste": 0.6, "general": 0.4}

        gw = CompositeEvalQueryGateway(
            redis_adapter=redis_adapter,
            pg_adapter=pg_adapter,
        )
        dist = await gw.get_intent_distribution(days=7)

        assert dist == {"waste": 0.6, "general": 0.4}

    async def test_get_intent_distribution_no_pg_returns_empty(self) -> None:
        """PG=None → 빈 dict."""
        redis_adapter = AsyncMock()

        gw = CompositeEvalQueryGateway(
            redis_adapter=redis_adapter,
            pg_adapter=None,
        )
        dist = await gw.get_intent_distribution(days=7)

        assert dist == {}

    async def test_get_recent_scores_pg_failure_returns_empty(self) -> None:
        """PG fallback 실패 시 빈 리스트."""
        redis_adapter = AsyncMock()
        redis_adapter.get_recent_scores.return_value = []
        pg_adapter = AsyncMock()
        pg_adapter.get_recent_scores.side_effect = Exception("PG timeout")

        gw = CompositeEvalQueryGateway(
            redis_adapter=redis_adapter,
            pg_adapter=pg_adapter,
        )
        scores = await gw.get_recent_scores("faithfulness", n=10)

        assert scores == []
