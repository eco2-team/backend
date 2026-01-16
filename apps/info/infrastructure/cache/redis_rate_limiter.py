"""Redis Rate Limiter Implementation.

Sliding Window Counter 알고리즘을 사용한 Rate Limiter.

데이터 구조:
- rate_limit:config:{source} → Hash (daily_limit, window_seconds)
- rate_limit:counter:{source}:{window_id} → String (호출 카운트)
"""

from __future__ import annotations

import logging
import time

from redis.asyncio import Redis

from info.application.ports.rate_limiter import (
    RateLimitConfig,
    RateLimiterPort,
    RateLimitStatus,
)

logger = logging.getLogger(__name__)

# Redis 키 프리픽스
CONFIG_KEY_PREFIX = "rate_limit:config:"
COUNTER_KEY_PREFIX = "rate_limit:counter:"

# 기본 설정
DEFAULT_LIMITS: dict[str, RateLimitConfig] = {
    "naver": RateLimitConfig(source="naver", daily_limit=25000),
    "newsdata": RateLimitConfig(source="newsdata", daily_limit=200),
}


class RedisRateLimiter(RateLimiterPort):
    """Redis 기반 Rate Limiter.

    Sliding Window Counter 알고리즘을 사용하여 정확한 rate limiting 수행.
    """

    def __init__(self, redis: Redis, default_configs: dict[str, RateLimitConfig] | None = None):
        """초기화.

        Args:
            redis: Redis 클라이언트
            default_configs: 소스별 기본 설정 (없으면 DEFAULT_LIMITS 사용)
        """
        self._redis = redis
        self._configs = default_configs or DEFAULT_LIMITS.copy()

    def _config_key(self, source: str) -> str:
        """설정 키 생성."""
        return f"{CONFIG_KEY_PREFIX}{source}"

    def _counter_key(self, source: str, window_id: int) -> str:
        """카운터 키 생성."""
        return f"{COUNTER_KEY_PREFIX}{source}:{window_id}"

    def _get_window_id(self, window_seconds: int) -> int:
        """현재 윈도우 ID 계산."""
        return int(time.time()) // window_seconds

    def _get_reset_at(self, window_id: int, window_seconds: int) -> int:
        """윈도우 리셋 시간 계산."""
        return (window_id + 1) * window_seconds

    async def configure(self, config: RateLimitConfig) -> None:
        """Rate Limit 설정 저장.

        Args:
            config: Rate Limit 설정
        """
        self._configs[config.source] = config

        config_key = self._config_key(config.source)
        await self._redis.hset(
            config_key,
            mapping={
                "daily_limit": str(config.daily_limit),
                "window_seconds": str(config.window_seconds),
            },
        )

        logger.info(
            "Rate limit configured",
            extra={
                "source": config.source,
                "daily_limit": config.daily_limit,
                "window_seconds": config.window_seconds,
            },
        )

    async def _get_config(self, source: str) -> RateLimitConfig:
        """소스 설정 조회."""
        # 메모리 캐시 먼저 확인
        if source in self._configs:
            return self._configs[source]

        # Redis에서 조회
        config_key = self._config_key(source)
        data = await self._redis.hgetall(config_key)

        if data:
            config = RateLimitConfig(
                source=source,
                daily_limit=int(data.get("daily_limit", 1000)),
                window_seconds=int(data.get("window_seconds", 86400)),
            )
            self._configs[source] = config
            return config

        # 기본값 사용 (안전한 기본값)
        return RateLimitConfig(source=source, daily_limit=1000)

    async def check_and_consume(self, source: str) -> RateLimitStatus:
        """호출 가능 여부 확인 및 카운터 증가.

        Lua 스크립트로 원자적 처리.

        Args:
            source: 소스 식별자

        Returns:
            Rate Limit 상태
        """
        config = await self._get_config(source)
        window_id = self._get_window_id(config.window_seconds)
        counter_key = self._counter_key(source, window_id)
        reset_at = self._get_reset_at(window_id, config.window_seconds)

        # Lua 스크립트로 원자적 처리
        lua_script = """
        local counter_key = KEYS[1]
        local limit = tonumber(ARGV[1])
        local window_seconds = tonumber(ARGV[2])

        local current = tonumber(redis.call('GET', counter_key) or '0')

        if current >= limit then
            return {0, current, 0}  -- not allowed
        end

        local new_count = redis.call('INCR', counter_key)
        if new_count == 1 then
            redis.call('EXPIRE', counter_key, window_seconds)
        end

        return {1, new_count, limit - new_count}  -- allowed, count, remaining
        """

        result = await self._redis.eval(
            lua_script,
            1,
            counter_key,
            config.daily_limit,
            config.window_seconds,
        )

        is_allowed, current, remaining = result

        status = RateLimitStatus(
            source=source,
            remaining=int(remaining),
            reset_at=reset_at,
            is_allowed=bool(is_allowed),
        )

        if not is_allowed:
            logger.warning(
                "Rate limit exceeded",
                extra={
                    "source": source,
                    "current": current,
                    "limit": config.daily_limit,
                    "reset_at": reset_at,
                },
            )

        return status

    async def get_status(self, source: str) -> RateLimitStatus:
        """현재 Rate Limit 상태 조회.

        Args:
            source: 소스 식별자

        Returns:
            Rate Limit 상태
        """
        config = await self._get_config(source)
        window_id = self._get_window_id(config.window_seconds)
        counter_key = self._counter_key(source, window_id)
        reset_at = self._get_reset_at(window_id, config.window_seconds)

        current = await self._redis.get(counter_key)
        current_count = int(current) if current else 0

        remaining = config.daily_limit - current_count
        is_allowed = remaining > 0

        return RateLimitStatus(
            source=source,
            remaining=max(0, remaining),
            reset_at=reset_at,
            is_allowed=is_allowed,
        )
