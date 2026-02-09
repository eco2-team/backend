"""RedisEvalCounter Unit Tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from chat_worker.infrastructure.persistence.eval.redis_eval_counter import (
    RedisEvalCounter,
)


@pytest.mark.eval_unit
class TestRedisEvalCounter:
    """RedisEvalCounter 테스트."""

    def _make_counter(
        self, redis: AsyncMock | None = None, interval: int = 100
    ) -> RedisEvalCounter:
        """테스트 팩토리."""
        return RedisEvalCounter(redis=redis or AsyncMock(), interval=interval)

    async def test_increment_and_check_returns_count(self) -> None:
        """increment_and_check()가 카운트를 반환하는지 검증."""
        redis = MagicMock()
        pipe = MagicMock()
        pipe.execute = AsyncMock(return_value=[42, True])
        redis.pipeline.return_value = pipe

        counter = self._make_counter(redis=redis, interval=100)
        count, should_calibrate = await counter.increment_and_check()

        assert count == 42
        assert should_calibrate is False

    async def test_increment_and_check_triggers_at_interval(self) -> None:
        """interval 배수에서 should_calibrate=True 반환."""
        redis = MagicMock()
        pipe = MagicMock()
        pipe.execute = AsyncMock(return_value=[100, True])
        redis.pipeline.return_value = pipe

        counter = self._make_counter(redis=redis, interval=100)
        count, should_calibrate = await counter.increment_and_check()

        assert count == 100
        assert should_calibrate is True

    async def test_increment_and_check_no_trigger_at_non_interval(self) -> None:
        """interval 비배수에서 should_calibrate=False."""
        redis = MagicMock()
        pipe = MagicMock()
        pipe.execute = AsyncMock(return_value=[99, True])
        redis.pipeline.return_value = pipe

        counter = self._make_counter(redis=redis, interval=100)
        count, should_calibrate = await counter.increment_and_check()

        assert count == 99
        assert should_calibrate is False

    async def test_increment_and_check_zero_interval_never_triggers(self) -> None:
        """interval=0이면 절대 트리거하지 않음."""
        redis = MagicMock()
        pipe = MagicMock()
        pipe.execute = AsyncMock(return_value=[100, True])
        redis.pipeline.return_value = pipe

        counter = self._make_counter(redis=redis, interval=0)
        count, should_calibrate = await counter.increment_and_check()

        assert count == 100
        assert should_calibrate is False

    async def test_increment_pipeline_calls(self) -> None:
        """INCR + EXPIRE pipeline 호출 검증."""
        redis = MagicMock()
        pipe = MagicMock()
        pipe.execute = AsyncMock(return_value=[1, True])
        redis.pipeline.return_value = pipe

        counter = self._make_counter(redis=redis)
        await counter.increment_and_check()

        pipe.incr.assert_called_once()
        pipe.expire.assert_called_once()
        pipe.execute.assert_called_once()

    async def test_get_count_returns_current(self) -> None:
        """get_count()가 현재 카운트를 반환."""
        redis = AsyncMock()
        redis.get.return_value = "55"

        counter = self._make_counter(redis=redis)
        count = await counter.get_count()

        assert count == 55

    async def test_get_count_returns_zero_when_missing(self) -> None:
        """키가 없으면 0을 반환."""
        redis = AsyncMock()
        redis.get.return_value = None

        counter = self._make_counter(redis=redis)
        count = await counter.get_count()

        assert count == 0

    async def test_interval_property(self) -> None:
        """interval 속성 접근 가능."""
        counter = self._make_counter(interval=50)
        assert counter.interval == 50

    @patch("chat_worker.infrastructure.persistence.eval.redis_eval_counter.datetime")
    async def test_key_format_includes_date(self, mock_dt) -> None:
        """키에 날짜가 포함되는지 검증."""
        from datetime import datetime, timezone

        mock_dt.now.return_value = datetime(2026, 2, 10, tzinfo=timezone.utc)
        mock_dt.side_effect = lambda *args, **kw: datetime(*args, **kw)

        key = RedisEvalCounter._make_key()
        assert "2026-02-10" in key
        assert key.startswith("eval:request_count:")
