"""Redis Stream Domain Event Bus - DomainEventBusPort 구현체.

시스템 내부 이벤트 전달용 Redis Streams 구현.

vs RedisProgressNotifier:
- ProgressNotifier: SSE/UI 피드백 (유실 가능)
- DomainEventBus: 시스템 연동 (전달 보장 필요)

향후 확장:
- Consumer Group을 사용하여 전달 보장
- Dead Letter Queue로 실패한 이벤트 재처리
- 별도 스트림 또는 MQ(RabbitMQ)로 분리 가능

Port: application/ports/events/domain_event_bus.py
"""

from __future__ import annotations

import json
import logging
import time
from typing import TYPE_CHECKING, Any

from chat_worker.application.ports.events.domain_event_bus import (
    DomainEventBusPort,
    JobStatus,
)

if TYPE_CHECKING:
    from redis.asyncio import Redis

logger = logging.getLogger(__name__)


class RedisStreamDomainEventBus(DomainEventBusPort):
    """Redis Streams 기반 도메인 이벤트 버스.

    시스템 내부 이벤트 전달.
    Consumer Group을 통한 전달 보장 가능.
    """

    def __init__(
        self,
        redis: "Redis",
        stream_name: str = "chat:domain_events",
        maxlen: int = 10000,
    ):
        """초기화.

        Args:
            redis: Redis 클라이언트
            stream_name: 도메인 이벤트 스트림 이름
            maxlen: 스트림 최대 길이
        """
        self._redis = redis
        self._stream_name = stream_name
        self._maxlen = maxlen
        logger.info(
            "RedisStreamDomainEventBus initialized",
            extra={"stream": stream_name, "maxlen": maxlen},
        )

    async def publish_status_changed(
        self,
        task_id: str,
        old_status: JobStatus,
        new_status: JobStatus,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """상태 변경 이벤트 발행."""
        event_data = {
            "event_type": "status_changed",
            "task_id": task_id,
            "old_status": old_status.value,
            "new_status": new_status.value,
            "timestamp": time.time(),
        }
        if metadata:
            event_data["metadata"] = json.dumps(metadata, ensure_ascii=False)

        await self._redis.xadd(
            self._stream_name,
            event_data,
            maxlen=self._maxlen,
        )

        logger.info(
            "Status changed event published",
            extra={
                "task_id": task_id,
                "old_status": old_status.value,
                "new_status": new_status.value,
            },
        )

    async def publish_job_completed(
        self,
        task_id: str,
        session_id: str,
        user_id: str,
        intent: str | None,
        answer: str | None,
    ) -> None:
        """작업 완료 이벤트 발행."""
        event_data = {
            "event_type": "job_completed",
            "task_id": task_id,
            "session_id": session_id,
            "user_id": user_id,
            "timestamp": time.time(),
        }
        if intent:
            event_data["intent"] = intent
        if answer:
            # 답변이 길 수 있으므로 요약만 저장
            event_data["answer_length"] = str(len(answer))
            event_data["answer_preview"] = answer[:200] if len(answer) > 200 else answer

        await self._redis.xadd(
            self._stream_name,
            event_data,
            maxlen=self._maxlen,
        )

        logger.info(
            "Job completed event published",
            extra={
                "task_id": task_id,
                "session_id": session_id,
                "intent": intent,
            },
        )

    async def publish_job_failed(
        self,
        task_id: str,
        session_id: str,
        user_id: str,
        error: str,
    ) -> None:
        """작업 실패 이벤트 발행."""
        event_data = {
            "event_type": "job_failed",
            "task_id": task_id,
            "session_id": session_id,
            "user_id": user_id,
            "error": error[:500] if len(error) > 500 else error,  # 에러 길이 제한
            "timestamp": time.time(),
        }

        await self._redis.xadd(
            self._stream_name,
            event_data,
            maxlen=self._maxlen,
        )

        logger.warning(
            "Job failed event published",
            extra={
                "task_id": task_id,
                "session_id": session_id,
                "error": error[:100],
            },
        )
