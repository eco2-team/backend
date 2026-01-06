"""Event Publisher Redis Adapter - Redis Streams 이벤트 발행.

domains 의존성 제거 - 내부 messaging 모듈 사용.
"""

from __future__ import annotations

import logging
from typing import Any

from scan.application.classify.ports.event_publisher import EventPublisher
from scan.infrastructure.messaging import (
    get_sync_streams_client,
    publish_stage_event,
)

logger = logging.getLogger(__name__)


class EventPublisherRedis(EventPublisher):
    """Redis Streams 이벤트 발행 Adapter.

    queued 이벤트 발행용 (작업 제출 시).
    Event Router가 이 Streams를 소비하여 Pub/Sub로 릴레이합니다.
    """

    def __init__(self, redis_url: str | None = None):
        """초기화.

        Args:
            redis_url: Redis URL (미사용, 환경변수에서 가져옴)
        """
        self._redis_url = redis_url
        self._sync_client = None

    def publish_stage_event(
        self,
        job_id: str,
        stage: str,
        status: str,
        progress: int,
        result: dict[str, Any] | None = None,
    ) -> None:
        """파이프라인 스테이지 이벤트 발행."""
        redis_client = self.get_sync_client()
        publish_stage_event(
            redis_client=redis_client,
            job_id=job_id,
            stage=stage,
            status=status,
            progress=progress,
            result=result,
        )

        logger.debug(
            "stage_event_published",
            extra={
                "job_id": job_id,
                "stage": stage,
                "status": status,
                "progress": progress,
            },
        )

    def get_sync_client(self) -> Any:
        """동기 Redis 클라이언트 반환."""
        if self._sync_client is None:
            self._sync_client = get_sync_streams_client()
        return self._sync_client
