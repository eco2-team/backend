"""Circuit Breaker - 연속 실패 시 빠른 실패 패턴.

Circuit Breaker 상태 머신:
- CLOSED: 정상 상태, 요청 통과
- OPEN: 실패 임계값 도달, 요청 즉시 거부
- HALF_OPEN: 복구 테스트 중, 제한된 요청 허용

왜 Circuit Breaker가 필요한가?
1. 빠른 실패: 장애 서비스에 반복 요청 방지
2. 부하 감소: 장애 전파 차단
3. 자동 복구: 서비스 복구 시 자동 재개

Clean Architecture:
- Port: application/ports/circuit_breaker.py (추상화)
- Adapter: 이 파일 (구현체)

Thread Safety:
- CircuitBreaker: asyncio.Lock 사용 (async context)
- CircuitBreakerRegistry: threading.Lock 사용 (sync get, async 호환)
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from enum import Enum
from typing import TYPE_CHECKING

from chat_worker.application.ports.circuit_breaker import (
    CircuitBreakerPort,
    CircuitBreakerRegistryPort,
)

if TYPE_CHECKING:
    from chat_worker.infrastructure.orchestration.langgraph.policies.node_policy import (
        NodePolicy,
    )

logger = logging.getLogger(__name__)


class CircuitState(str, Enum):
    """Circuit Breaker 상태."""

    CLOSED = "closed"
    """정상 상태 - 요청 통과."""

    OPEN = "open"
    """차단 상태 - 요청 즉시 거부."""

    HALF_OPEN = "half_open"
    """반열림 상태 - 복구 테스트 중."""


class CircuitBreakerOpen(Exception):
    """Circuit Breaker 열림 상태 예외."""

    def __init__(self, name: str, retry_after: float):
        self.name = name
        self.retry_after = retry_after
        super().__init__(f"Circuit breaker '{name}' is open. Retry after {retry_after:.1f}s")


class CircuitBreaker(CircuitBreakerPort):
    """Circuit Breaker 구현 (CircuitBreakerPort Adapter).

    연속 실패 시 빠른 실패로 시스템 보호.

    Attributes:
        name: Circuit 이름 (노드 이름)
        threshold: 실패 임계값
        recovery_timeout: 복구 시도 대기 시간 (초)
        half_open_max_calls: HALF_OPEN 상태에서 최대 허용 호출

    Example:
        >>> cb = CircuitBreaker("waste_rag", threshold=5)
        >>> async with cb.protect():
        ...     result = await some_operation()
    """

    def __init__(
        self,
        name: str,
        threshold: int = 5,
        recovery_timeout: float = 30.0,
        half_open_max_calls: int = 1,
    ):
        self.name = name
        self.threshold = threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time: float = 0.0
        self._half_open_calls = 0
        self._lock = asyncio.Lock()

    @property
    def state(self) -> CircuitState:
        """현재 상태 (시간 기반 전환 포함)."""
        if self._state == CircuitState.OPEN:
            # recovery_timeout 경과 시 HALF_OPEN으로 전환
            if time.time() - self._last_failure_time >= self.recovery_timeout:
                return CircuitState.HALF_OPEN
        return self._state

    @property
    def is_open(self) -> bool:
        """차단 상태 여부."""
        return self.state == CircuitState.OPEN

    @property
    def is_closed(self) -> bool:
        """정상 상태 여부."""
        return self.state == CircuitState.CLOSED

    async def allow_request(self) -> bool:
        """요청 허용 여부 확인.

        Returns:
            True if request is allowed, False otherwise
        """
        async with self._lock:
            current_state = self.state

            if current_state == CircuitState.CLOSED:
                return True

            if current_state == CircuitState.OPEN:
                return False

            # HALF_OPEN: 제한된 요청만 허용
            if self._half_open_calls < self.half_open_max_calls:
                self._half_open_calls += 1
                return True

            return False

    async def record_success(self) -> None:
        """성공 기록 - 상태 리셋."""
        async with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                # HALF_OPEN에서 성공하면 CLOSED로 전환
                logger.info(
                    "Circuit breaker recovered",
                    extra={"cb_name": self.name, "previous_state": "half_open"},
                )
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._half_open_calls = 0

    async def record_failure(self) -> None:
        """실패 기록 - 임계값 도달 시 OPEN."""
        async with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()

            if self._state == CircuitState.HALF_OPEN:
                # HALF_OPEN에서 실패하면 다시 OPEN
                self._state = CircuitState.OPEN
                self._half_open_calls = 0
                logger.warning(
                    "Circuit breaker reopened after half-open failure",
                    extra={"cb_name": self.name},
                )
                return

            if self._failure_count >= self.threshold:
                self._state = CircuitState.OPEN
                logger.warning(
                    "Circuit breaker opened",
                    extra={
                        "name": self.name,
                        "failure_count": self._failure_count,
                        "threshold": self.threshold,
                    },
                )

    def retry_after(self) -> float:
        """OPEN 상태에서 다음 시도까지 남은 시간 (초)."""
        if self._state != CircuitState.OPEN:
            return 0.0
        elapsed = time.time() - self._last_failure_time
        return max(0.0, self.recovery_timeout - elapsed)

    @classmethod
    def from_policy(cls, policy: "NodePolicy") -> "CircuitBreaker":
        """NodePolicy에서 CircuitBreaker 생성.

        Args:
            policy: 노드 정책

        Returns:
            설정된 CircuitBreaker
        """
        return cls(
            name=policy.name,
            threshold=policy.cb_threshold,
        )


class CircuitBreakerRegistry(CircuitBreakerRegistryPort):
    """Circuit Breaker 레지스트리 (싱글톤, CircuitBreakerRegistryPort Adapter).

    모든 노드의 Circuit Breaker를 중앙 관리.

    Thread Safety:
    - threading.Lock 사용으로 동시 접근 시 race condition 방지
    - 싱글톤 생성과 get() 모두 lock으로 보호

    Example:
        >>> registry = CircuitBreakerRegistry()
        >>> cb = registry.get("waste_rag", threshold=5)
        >>> # 같은 이름으로 다시 요청하면 동일 인스턴스 반환
    """

    _instance: "CircuitBreakerRegistry | None" = None
    _creation_lock = threading.Lock()

    def __new__(cls) -> "CircuitBreakerRegistry":
        if cls._instance is None:
            with cls._creation_lock:
                # Double-checked locking
                if cls._instance is None:
                    instance = super().__new__(cls)
                    instance._breakers: dict[str, CircuitBreaker] = {}
                    instance._registry_lock = threading.Lock()
                    cls._instance = instance
        return cls._instance

    def get(
        self,
        name: str,
        threshold: int = 5,
        recovery_timeout: float = 30.0,
    ) -> CircuitBreaker:
        """Circuit Breaker 조회 또는 생성.

        Thread-safe: _registry_lock으로 동시 접근 보호.

        Args:
            name: Circuit 이름
            threshold: 실패 임계값 (새로 생성 시만 적용)
            recovery_timeout: 복구 대기 시간

        Returns:
            CircuitBreaker 인스턴스
        """
        # Fast path: 이미 존재하면 lock 없이 반환
        if name in self._breakers:
            return self._breakers[name]

        # Slow path: 생성 시에만 lock
        with self._registry_lock:
            # Double-checked locking
            if name not in self._breakers:
                self._breakers[name] = CircuitBreaker(
                    name=name,
                    threshold=threshold,
                    recovery_timeout=recovery_timeout,
                )
            return self._breakers[name]

    def get_from_policy(self, policy: "NodePolicy") -> CircuitBreaker:
        """NodePolicy로 Circuit Breaker 조회 또는 생성.

        Args:
            policy: 노드 정책

        Returns:
            CircuitBreaker 인스턴스
        """
        return self.get(
            name=policy.name,
            threshold=policy.cb_threshold,
        )

    def get_all_states(self) -> dict[str, CircuitState]:
        """모든 Circuit Breaker 상태 조회."""
        with self._registry_lock:
            return {name: cb.state for name, cb in self._breakers.items()}

    def reset_all(self) -> None:
        """모든 Circuit Breaker 리셋 (테스트용)."""
        with self._registry_lock:
            self._breakers.clear()

    @classmethod
    def reset_instance(cls) -> None:
        """싱글톤 인스턴스 리셋 (테스트용).

        Note: 테스트 간 격리를 위해 사용.
        """
        with cls._creation_lock:
            cls._instance = None


__all__ = [
    "CircuitBreaker",
    "CircuitBreakerOpen",
    "CircuitBreakerRegistry",
    "CircuitState",
]
