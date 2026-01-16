"""Node Result DTO - 노드 실행 결과 표준 스키마.

모든 LangGraph 노드의 실행 결과를 표준화합니다.

왜 표준 스키마가 필요한가?
- Aggregator: 어떤 컨텍스트가 성공/실패했는지 일관된 방식으로 확인
- 로깅: 구조화된 로그로 모니터링/디버깅
- 메트릭: 성공률, 지연 시간 등 측정
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class NodeStatus(str, Enum):
    """노드 실행 상태."""

    SUCCESS = "success"
    """정상 완료."""

    FAILED = "failed"
    """실패 (재시도 불가능)."""

    SKIPPED = "skipped"
    """스킵됨 (조건 미충족 등)."""

    TIMEOUT = "timeout"
    """타임아웃 발생."""

    CIRCUIT_OPEN = "circuit_open"
    """Circuit Breaker 열림 상태로 실행 안함."""


@dataclass
class NodeResult:
    """노드 실행 결과 표준 스키마.

    모든 노드는 이 스키마를 따르는 결과를 반환해야 합니다.

    Attributes:
        node_name: 노드 이름 (예: "waste_rag", "character")
        status: 실행 상태
        data: 성공 시 결과 데이터 (dict)
        error_message: 실패 시 에러 메시지
        latency_ms: 실행 시간 (밀리초)
        retry_count: 재시도 횟수
        timestamp: 실행 완료 시간

    Example:
        >>> result = NodeResult.success(
        ...     node_name="waste_rag",
        ...     data={"context": "플라스틱은 재활용..."},
        ...     latency_ms=150,
        ... )
        >>> result.is_success
        True
    """

    node_name: str
    status: NodeStatus
    data: dict[str, Any] = field(default_factory=dict)
    error_message: str | None = None
    latency_ms: float = 0.0
    retry_count: int = 0
    timestamp: datetime = field(default_factory=datetime.now)

    @property
    def is_success(self) -> bool:
        """성공 여부."""
        return self.status == NodeStatus.SUCCESS

    @property
    def is_failed(self) -> bool:
        """실패 여부 (timeout, circuit_open 포함)."""
        return self.status in (
            NodeStatus.FAILED,
            NodeStatus.TIMEOUT,
            NodeStatus.CIRCUIT_OPEN,
        )

    @property
    def is_skipped(self) -> bool:
        """스킵 여부."""
        return self.status == NodeStatus.SKIPPED

    @classmethod
    def success(
        cls,
        node_name: str,
        data: dict[str, Any],
        latency_ms: float = 0.0,
        retry_count: int = 0,
    ) -> "NodeResult":
        """성공 결과 생성."""
        return cls(
            node_name=node_name,
            status=NodeStatus.SUCCESS,
            data=data,
            latency_ms=latency_ms,
            retry_count=retry_count,
        )

    @classmethod
    def failed(
        cls,
        node_name: str,
        error_message: str,
        latency_ms: float = 0.0,
        retry_count: int = 0,
    ) -> "NodeResult":
        """실패 결과 생성."""
        return cls(
            node_name=node_name,
            status=NodeStatus.FAILED,
            error_message=error_message,
            latency_ms=latency_ms,
            retry_count=retry_count,
        )

    @classmethod
    def timeout(
        cls,
        node_name: str,
        latency_ms: float,
        retry_count: int = 0,
    ) -> "NodeResult":
        """타임아웃 결과 생성."""
        return cls(
            node_name=node_name,
            status=NodeStatus.TIMEOUT,
            error_message=f"Timeout after {latency_ms:.0f}ms",
            latency_ms=latency_ms,
            retry_count=retry_count,
        )

    @classmethod
    def circuit_open(cls, node_name: str) -> "NodeResult":
        """Circuit Breaker 열림 상태 결과 생성."""
        return cls(
            node_name=node_name,
            status=NodeStatus.CIRCUIT_OPEN,
            error_message="Circuit breaker is open",
        )

    @classmethod
    def skipped(cls, node_name: str, reason: str = "") -> "NodeResult":
        """스킵 결과 생성."""
        return cls(
            node_name=node_name,
            status=NodeStatus.SKIPPED,
            error_message=reason if reason else None,
        )

    def to_dict(self) -> dict:
        """직렬화용 딕셔너리 변환."""
        return {
            "node_name": self.node_name,
            "status": self.status.value,
            "data": self.data,
            "error_message": self.error_message,
            "latency_ms": self.latency_ms,
            "retry_count": self.retry_count,
            "timestamp": self.timestamp.isoformat(),
        }


__all__ = ["NodeResult", "NodeStatus"]
