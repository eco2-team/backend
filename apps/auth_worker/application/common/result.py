"""Command Result.

MQ의 ack/nack 정책을 Application 계층의 언어로 추상화합니다.

블로그 참고: https://rooftopsnow.tistory.com/126
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto


class ResultStatus(Enum):
    """Command 실행 결과 상태.

    MQ semantics를 Application 언어로 추상화:
    - SUCCESS: 성공 → ack
    - RETRYABLE: 일시적 실패 → nack + requeue
    - DROP: 영구적 실패 → ack (메시지 버림)
    """

    SUCCESS = auto()
    RETRYABLE = auto()
    DROP = auto()


@dataclass(frozen=True)
class CommandResult:
    """Command 실행 결과.

    핵심 원칙:
    - Command가 재시도 가능 여부를 판단
    - ConsumerAdapter가 어떻게 재시도할지를 결정
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
        """메시지 버림 여부."""
        return self.status == ResultStatus.DROP

    @classmethod
    def success(cls, message: str | None = None) -> CommandResult:
        """성공 결과 생성."""
        return cls(status=ResultStatus.SUCCESS, message=message)

    @classmethod
    def retryable(cls, message: str) -> CommandResult:
        """재시도 가능 결과 생성."""
        return cls(status=ResultStatus.RETRYABLE, message=message)

    @classmethod
    def drop(cls, message: str) -> CommandResult:
        """버림 결과 생성."""
        return cls(status=ResultStatus.DROP, message=message)
