"""Rate Limiter Unit Tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from info.application.ports.rate_limiter import RateLimitConfig, RateLimitStatus


class TestRateLimiterPort:
    """RateLimiterPort 기본 테스트."""

    def test_rate_limit_config_frozen(self) -> None:
        """RateLimitConfig는 불변 객체."""
        config = RateLimitConfig(source="naver", daily_limit=25000)
        assert config.source == "naver"
        assert config.daily_limit == 25000
        assert config.window_seconds == 86400  # 기본값

        with pytest.raises(AttributeError):
            config.daily_limit = 1000  # type: ignore

    def test_rate_limit_config_custom_window(self) -> None:
        """커스텀 윈도우 설정 테스트."""
        config = RateLimitConfig(
            source="newsdata",
            daily_limit=200,
            window_seconds=3600,  # 1시간
        )
        assert config.window_seconds == 3600

    def test_rate_limit_status_allowed(self) -> None:
        """허용 상태 테스트."""
        status = RateLimitStatus(
            source="naver",
            remaining=24999,
            reset_at=1737100800,
            is_allowed=True,
        )
        assert status.is_allowed is True
        assert status.remaining == 24999

    def test_rate_limit_status_blocked(self) -> None:
        """차단 상태 테스트."""
        status = RateLimitStatus(
            source="newsdata",
            remaining=0,
            reset_at=1737100800,
            is_allowed=False,
        )
        assert status.is_allowed is False
        assert status.remaining == 0


class TestFetchNewsCommandWithRateLimiter:
    """FetchNewsCommand Rate Limiter 통합 테스트."""

    @pytest.fixture
    def mock_rate_limiter(self) -> AsyncMock:
        """Mock RateLimiterPort."""
        mock = AsyncMock()
        mock.get_status = AsyncMock(
            return_value=RateLimitStatus(
                source="test",
                remaining=100,
                reset_at=1737100800,
                is_allowed=True,
            )
        )
        mock.check_and_consume = AsyncMock(
            return_value=RateLimitStatus(
                source="test",
                remaining=99,
                reset_at=1737100800,
                is_allowed=True,
            )
        )
        return mock

    @pytest.fixture
    def mock_rate_limited(self) -> AsyncMock:
        """Rate Limited 상태의 Mock."""
        mock = AsyncMock()
        mock.get_status = AsyncMock(
            return_value=RateLimitStatus(
                source="test",
                remaining=0,
                reset_at=1737100800,
                is_allowed=False,
            )
        )
        mock.check_and_consume = AsyncMock(
            return_value=RateLimitStatus(
                source="test",
                remaining=0,
                reset_at=1737100800,
                is_allowed=False,
            )
        )
        return mock

    @pytest.mark.asyncio
    async def test_filter_rate_limited_sources_allows_all(
        self,
        mock_news_cache: AsyncMock,
        mock_news_source: AsyncMock,
        mock_aggregator: MagicMock,
        mock_rate_limiter: AsyncMock,
    ) -> None:
        """Rate Limit 내에서 모든 소스 허용."""
        from info.application.commands.fetch_news_command import FetchNewsCommand

        command = FetchNewsCommand(
            news_sources=[mock_news_source],
            news_cache=mock_news_cache,
            aggregator=mock_aggregator,
            cache_ttl=3600,
            rate_limiter=mock_rate_limiter,
        )

        result = await command._filter_rate_limited_sources()

        assert len(result) == 1
        mock_rate_limiter.get_status.assert_called_once_with("mock_source")

    @pytest.mark.asyncio
    async def test_filter_rate_limited_sources_filters_blocked(
        self,
        mock_news_cache: AsyncMock,
        mock_news_source: AsyncMock,
        mock_aggregator: MagicMock,
        mock_rate_limited: AsyncMock,
    ) -> None:
        """Rate Limit 초과 소스 필터링."""
        from info.application.commands.fetch_news_command import FetchNewsCommand

        command = FetchNewsCommand(
            news_sources=[mock_news_source],
            news_cache=mock_news_cache,
            aggregator=mock_aggregator,
            cache_ttl=3600,
            rate_limiter=mock_rate_limited,
        )

        result = await command._filter_rate_limited_sources()

        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_filter_without_rate_limiter(
        self,
        mock_news_cache: AsyncMock,
        mock_news_source: AsyncMock,
        mock_aggregator: MagicMock,
    ) -> None:
        """Rate Limiter 없을 때 모든 소스 반환."""
        from info.application.commands.fetch_news_command import FetchNewsCommand

        command = FetchNewsCommand(
            news_sources=[mock_news_source],
            news_cache=mock_news_cache,
            aggregator=mock_aggregator,
            cache_ttl=3600,
        )

        result = await command._filter_rate_limited_sources()

        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_fetch_with_rate_limit_allowed(
        self,
        mock_news_cache: AsyncMock,
        mock_news_source: AsyncMock,
        mock_aggregator: MagicMock,
        mock_rate_limiter: AsyncMock,
        sample_article,
    ) -> None:
        """Rate Limit 허용 시 정상 fetch."""
        from info.application.commands.fetch_news_command import FetchNewsCommand

        mock_news_source.fetch_news.return_value = [sample_article]

        command = FetchNewsCommand(
            news_sources=[mock_news_source],
            news_cache=mock_news_cache,
            aggregator=mock_aggregator,
            cache_ttl=3600,
            rate_limiter=mock_rate_limiter,
        )

        result = await command._fetch_with_rate_limit(mock_news_source, "test query")

        assert result == [sample_article]
        mock_rate_limiter.check_and_consume.assert_called_once()

    @pytest.mark.asyncio
    async def test_fetch_with_rate_limit_blocked(
        self,
        mock_news_cache: AsyncMock,
        mock_news_source: AsyncMock,
        mock_aggregator: MagicMock,
        mock_rate_limited: AsyncMock,
    ) -> None:
        """Rate Limit 차단 시 None 반환."""
        from info.application.commands.fetch_news_command import FetchNewsCommand

        command = FetchNewsCommand(
            news_sources=[mock_news_source],
            news_cache=mock_news_cache,
            aggregator=mock_aggregator,
            cache_ttl=3600,
            rate_limiter=mock_rate_limited,
        )

        result = await command._fetch_with_rate_limit(mock_news_source, "test query")

        assert result is None
        mock_news_source.fetch_news.assert_not_called()
