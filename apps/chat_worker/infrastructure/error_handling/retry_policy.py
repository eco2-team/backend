"""Retry Policy - 재시도 정책.

알고리즘:
- Exponential Backoff: 지수적 증가
- Jitter: 랜덤 지연 추가 (Thundering Herd 방지)

예외 분류:
- Transient: 재시도 가능 (네트워크, 타임아웃)
- Permanent: 재시도 불가 (유효성 검사, 인증)
"""

from __future__ import annotations

import asyncio
import logging
import random
from dataclasses import dataclass
from functools import wraps
from typing import Awaitable, Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


# 재시도 가능한 예외들
TRANSIENT_EXCEPTIONS = (
    TimeoutError,
    ConnectionError,
    asyncio.TimeoutError,
)


@dataclass
class RetryPolicy:
    """재시도 정책 설정."""

    max_retries: int = 3
    base_delay: float = 1.0  # 초
    max_delay: float = 30.0  # 초
    exponential_base: float = 2.0
    jitter: bool = True


class ExponentialBackoff:
    """Exponential Backoff 재시도 실행기."""

    def __init__(self, policy: RetryPolicy | None = None):
        """초기화.

        Args:
            policy: 재시도 정책 (None이면 기본값)
        """
        self._policy = policy or RetryPolicy()

    def calculate_delay(self, attempt: int) -> float:
        """재시도 지연 시간 계산.

        Args:
            attempt: 현재 시도 횟수 (0부터 시작)

        Returns:
            지연 시간 (초)
        """
        delay = self._policy.base_delay * (self._policy.exponential_base**attempt)
        delay = min(delay, self._policy.max_delay)

        if self._policy.jitter:
            # ±25% 랜덤 지터
            jitter_range = delay * 0.25
            delay += random.uniform(-jitter_range, jitter_range)

        return max(0, delay)

    def is_retriable(self, error: Exception) -> bool:
        """재시도 가능한 예외인지 확인.

        Args:
            error: 발생한 예외

        Returns:
            재시도 가능 여부
        """
        return isinstance(error, TRANSIENT_EXCEPTIONS)

    async def execute(
        self,
        func: Callable[..., Awaitable[T]],
        *args,
        **kwargs,
    ) -> T:
        """재시도 로직과 함께 함수 실행.

        Args:
            func: 실행할 async 함수
            *args: 위치 인자
            **kwargs: 키워드 인자

        Returns:
            함수 실행 결과

        Raises:
            마지막 예외 (재시도 모두 실패 시)
        """
        last_error: Exception | None = None

        for attempt in range(self._policy.max_retries + 1):
            try:
                return await func(*args, **kwargs)

            except Exception as e:
                last_error = e

                # 재시도 불가능한 예외
                if not self.is_retriable(e):
                    logger.warning(
                        "retry_permanent_error",
                        extra={
                            "attempt": attempt,
                            "error_type": type(e).__name__,
                            "error": str(e),
                        },
                    )
                    raise

                # 마지막 시도였으면 예외 발생
                if attempt >= self._policy.max_retries:
                    logger.error(
                        "retry_exhausted",
                        extra={
                            "attempts": attempt + 1,
                            "error_type": type(e).__name__,
                            "error": str(e),
                        },
                    )
                    raise

                # 재시도 대기
                delay = self.calculate_delay(attempt)
                logger.info(
                    "retry_scheduled",
                    extra={
                        "attempt": attempt + 1,
                        "max_retries": self._policy.max_retries,
                        "delay_seconds": round(delay, 2),
                        "error_type": type(e).__name__,
                    },
                )
                await asyncio.sleep(delay)

        # 여기 도달하면 안되지만 안전장치
        if last_error:
            raise last_error
        raise RuntimeError("Unexpected retry state")


def with_retry(
    policy: RetryPolicy | None = None,
) -> Callable[[Callable[..., Awaitable[T]]], Callable[..., Awaitable[T]]]:
    """재시도 데코레이터.

    Usage:
        @with_retry(RetryPolicy(max_retries=5))
        async def fetch_data():
            ...
    """

    def decorator(
        func: Callable[..., Awaitable[T]],
    ) -> Callable[..., Awaitable[T]]:
        backoff = ExponentialBackoff(policy)

        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            return await backoff.execute(func, *args, **kwargs)

        return wrapper

    return decorator
