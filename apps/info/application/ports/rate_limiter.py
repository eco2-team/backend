"""Rate Limiter Port.

외부 API 호출 제한을 위한 Rate Limiter 추상화.
소스별 일일 호출 제한 관리.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class RateLimitConfig:
    """Rate Limit 설정.

    Attributes:
        source: 소스 식별자 (예: "naver", "newsdata")
        daily_limit: 일일 최대 호출 수
        window_seconds: 윈도우 크기 (기본 24시간)
    """

    source: str
    daily_limit: int
    window_seconds: int = 86400  # 24시간


@dataclass(frozen=True)
class RateLimitStatus:
    """Rate Limit 상태.

    Attributes:
        source: 소스 식별자
        remaining: 남은 호출 수
        reset_at: 리셋 시간 (Unix timestamp)
        is_allowed: 호출 가능 여부
    """

    source: str
    remaining: int
    reset_at: int
    is_allowed: bool


class RateLimiterPort(ABC):
    """Rate Limiter 포트.

    소스별 API 호출 제한을 관리하는 인터페이스.
    """

    @abstractmethod
    async def check_and_consume(self, source: str) -> RateLimitStatus:
        """호출 가능 여부 확인 및 카운터 증가.

        Args:
            source: 소스 식별자

        Returns:
            Rate Limit 상태
        """
        pass

    @abstractmethod
    async def get_status(self, source: str) -> RateLimitStatus:
        """현재 Rate Limit 상태 조회.

        Args:
            source: 소스 식별자

        Returns:
            Rate Limit 상태
        """
        pass

    @abstractmethod
    async def configure(self, config: RateLimitConfig) -> None:
        """Rate Limit 설정.

        Args:
            config: Rate Limit 설정
        """
        pass
