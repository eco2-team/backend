"""Circuit Breaker Port - 회로 차단기 추상화.

Infrastructure의 CircuitBreaker 구현을 추상화하여
Application/Node에서 테스트 가능하도록 합니다.

Clean Architecture:
- Port: 이 파일 (추상화)
- Adapter: infrastructure/resilience/circuit_breaker.py (구현체)

Note:
    get_from_policy()는 Infrastructure 레이어에서 NodePolicy를 사용하여
    CircuitBreaker를 조회하는 편의 메서드로, Port에서는 정의하지 않습니다.
    (Application → Infrastructure 의존 방지)
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class CircuitBreakerPort(ABC):
    """Circuit Breaker Port.

    노드 실행 시 회로 차단기 상태를 관리합니다.

    상태:
    - CLOSED: 정상 동작
    - OPEN: 차단 (즉시 실패)
    - HALF_OPEN: 복구 시도
    """

    @abstractmethod
    async def allow_request(self) -> bool:
        """요청 허용 여부 확인.

        Returns:
            True면 요청 허용, False면 차단
        """
        ...

    @abstractmethod
    async def record_success(self) -> None:
        """성공 기록."""
        ...

    @abstractmethod
    async def record_failure(self) -> None:
        """실패 기록."""
        ...

    @abstractmethod
    def retry_after(self) -> float:
        """재시도 가능 시간 (초).

        Returns:
            OPEN 상태에서 재시도까지 남은 시간, CLOSED면 0.0
        """
        ...


class CircuitBreakerRegistryPort(ABC):
    """Circuit Breaker Registry Port.

    노드별 CircuitBreaker 인스턴스를 관리합니다.
    """

    @abstractmethod
    def get(self, name: str, threshold: int = 5) -> CircuitBreakerPort:
        """이름으로 CircuitBreaker 조회/생성.

        Args:
            name: Circuit Breaker 이름
            threshold: 실패 임계값

        Returns:
            CircuitBreaker 인스턴스
        """
        ...


__all__ = [
    "CircuitBreakerPort",
    "CircuitBreakerRegistryPort",
]
