"""Event Publisher Redis Adapter - Redis Streams 이벤트 발행."""

from __future__ import annotations

import logging
from typing import Any

from apps.scan.application.classify.ports.event_publisher import EventPublisher

logger = logging.getLogger(__name__)


class EventPublisherRedis(EventPublisher):
    """Redis Streams 이벤트 발행 Adapter.

    기존 domains/_shared/events 모듈을 래핑하여 정합성을 유지합니다.

    Note:
        Worker에서 사용하는 동기 버전입니다.
        Event Router가 이 Streams를 소비하여 Pub/Sub로 릴레이합니다.
    """

    def __init__(self, redis_url: str | None = None):
        """초기화.

        Args:
            redis_url: Redis URL (None이면 환경변수에서 가져옴)
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
        """파이프라인 스테이지 이벤트 발행.

        기존 publish_stage_event 함수를 사용하여 정합성 유지.
        """
        from domains._shared.events import (
            publish_stage_event as _publish_stage_event,
        )

        redis_client = self.get_sync_client()
        _publish_stage_event(
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
        """동기 Redis 클라이언트 반환.

        Celery Worker에서 재사용합니다.
        """
        if self._sync_client is None:
            from domains._shared.events import get_sync_redis_client

            self._sync_client = get_sync_redis_client()
        return self._sync_client
