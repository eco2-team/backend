"""Command Result.

Celery Task의 성공/실패/재시도 정책을 Application 계층의 언어로 추상화합니다.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto


class ResultStatus(Enum):
    """Command 실행 결과 상태.

    Celery semantics를 Application 언어로 추상화:
    - SUCCESS: 성공
    - RETRYABLE: 일시적 실패 → Celery retry
    - DROP: 영구적 실패 → 로깅 후 종료
    """

    SUCCESS = auto()
    RETRYABLE = auto()
    DROP = auto()


@dataclass(frozen=True)
class CommandResult:
    """Command 실행 결과.

    핵심 원칙:
    - Command가 재시도 가능 여부를 판단
    - Celery Task가 어떻게 재시도할지를 결정
    """

    status: ResultStatus
    message: str | None = None
    processed: int = 0
    upserted: int = 0

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
    def success(
        cls, *, processed: int = 0, upserted: int = 0, message: str | None = None
    ) -> CommandResult:
        """성공 결과 생성."""
        return cls(
            status=ResultStatus.SUCCESS,
            message=message,
            processed=processed,
            upserted=upserted,
        )

    @classmethod
    def retryable(cls, message: str) -> CommandResult:
        """재시도 가능 결과 생성."""
        return cls(status=ResultStatus.RETRYABLE, message=message)

    @classmethod
    def drop(cls, message: str) -> CommandResult:
        """버림 결과 생성."""
        return cls(status=ResultStatus.DROP, message=message)
