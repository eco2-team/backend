"""Domain Event Bus Port - 시스템 간 이벤트.

시스템 내부 이벤트 전달용.

책임:
- 작업 상태 변경 (queued → running → completed/failed)
- Human-in-the-Loop 상태 (waiting_human)
- 메트릭/감사 로그용 이벤트

vs ProgressNotifier:
- ProgressNotifier: 사용자 피드백 (SSE → Frontend)
- DomainEventBus: 시스템 연동 (MQ → 다른 서비스, 메트릭)

향후 확장:
- 작업 완료 시 알림 서비스 트리거
- 실패 시 경보 시스템 연동
- 메트릭 수집 (Prometheus)
"""

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any


class JobStatus(str, Enum):
    """작업 상태."""

    QUEUED = "queued"
    RUNNING = "running"
    WAITING_HUMAN = "waiting_human"
    COMPLETED = "completed"
    FAILED = "failed"


class DomainEventBusPort(ABC):
    """도메인 이벤트 버스 포트.

    시스템 내부 이벤트 전달.
    """

    @abstractmethod
    async def publish_status_changed(
        self,
        task_id: str,
        old_status: JobStatus,
        new_status: JobStatus,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """상태 변경 이벤트 발행.

        Args:
            task_id: 작업 ID
            old_status: 이전 상태
            new_status: 새 상태
            metadata: 추가 메타데이터
        """
        pass

    @abstractmethod
    async def publish_job_completed(
        self,
        task_id: str,
        session_id: str,
        user_id: str,
        intent: str | None,
        answer: str | None,
    ) -> None:
        """작업 완료 이벤트 발행.

        향후 확장:
        - 사용자 통계 업데이트
        - 세션 요약 생성
        - 알림 서비스 트리거
        """
        pass

    @abstractmethod
    async def publish_job_failed(
        self,
        task_id: str,
        session_id: str,
        user_id: str,
        error: str,
    ) -> None:
        """작업 실패 이벤트 발행.

        향후 확장:
        - 경보 시스템 연동
        - 실패 로그 수집
        """
        pass
