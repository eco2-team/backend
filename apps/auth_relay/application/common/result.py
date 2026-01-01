"""Command Result.

Relay 작업의 결과를 추상화합니다.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto


class ResultStatus(Enum):
    """Relay 결과 상태.

    - SUCCESS: 성공적으로 발행됨
    - RETRYABLE: 일시적 실패, 재시도 가능 (re-queue)
    - DROP: 영구적 실패, DLQ로 이동
    """

    SUCCESS = auto()
    RETRYABLE = auto()
    DROP = auto()


@dataclass(frozen=True)
class RelayResult:
    """Relay 작업 결과.

    핵심 원칙:
    - Command가 재시도 가능 여부를 판단
    - RelayLoop가 어떻게 처리할지를 결정
    """

    status: ResultStatus
    message: str | None = None

    @property
    def is_success(self) -> bool:
        """성공 여부."""
        return self.status == ResultStatus.SUCCESS

    @property
    def is_retryable(self) -> bool:
        """재시도 가능 여부."""
        return self.status == ResultStatus.RETRYABLE

    @property
    def should_drop(self) -> bool:
        """DLQ 이동 여부."""
        return self.status == ResultStatus.DROP

    @classmethod
    def success(cls, message: str | None = None) -> RelayResult:
        """성공 결과 생성."""
        return cls(status=ResultStatus.SUCCESS, message=message)

    @classmethod
    def retryable(cls, message: str) -> RelayResult:
        """재시도 가능 결과 생성."""
        return cls(status=ResultStatus.RETRYABLE, message=message)

    @classmethod
    def drop(cls, message: str) -> RelayResult:
        """DLQ 이동 결과 생성."""
        return cls(status=ResultStatus.DROP, message=message)
