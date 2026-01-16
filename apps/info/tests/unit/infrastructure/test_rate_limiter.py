"""Rate Limiter Unit Tests.

Rate Limiter는 info_worker로 이전됨.
이 테스트는 Port 인터페이스만 검증.
"""

from __future__ import annotations

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


# Note: FetchNewsCommand Rate Limiter 통합 테스트는 삭제됨
# Rate Limiter 기능이 info_worker로 이전되었기 때문
# info API는 Read-Only (Redis 캐시 → Postgres Fallback)
