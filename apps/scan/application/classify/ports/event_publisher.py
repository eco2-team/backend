"""Event Publisher Port - Redis Streams 이벤트 발행."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class EventPublisher(ABC):
    """Redis Streams 이벤트 발행 Port.

    Workers가 파이프라인 진행 상황을 발행하는 데 사용합니다.
    Event Router가 이를 소비하여 SSE Gateway로 릴레이합니다.
    """

    @abstractmethod
    def publish_stage_event(
        self,
        job_id: str,
        stage: str,
        status: str,
        progress: int,
        result: dict[str, Any] | None = None,
    ) -> None:
        """파이프라인 스테이지 이벤트 발행.

        Args:
            job_id: 작업 ID (UUID)
            stage: 파이프라인 단계 (queued, vision, rule, answer, reward, done)
            status: 상태 (started, completed, failed)
            progress: 진행률 (0-100)
            result: 결과 데이터 (completed/done 시)

        Note:
            Redis Streams에 XADD로 발행됩니다.
            scan:events:{shard} 스트림에 저장됩니다.
        """
        raise NotImplementedError

    @abstractmethod
    def get_sync_client(self) -> Any:
        """동기 Redis 클라이언트 반환 (Celery Worker용)."""
        raise NotImplementedError
