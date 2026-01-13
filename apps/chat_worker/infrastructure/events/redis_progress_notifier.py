"""Redis Progress Notifier - ProgressNotifierPort 구현체.

SSE 스트리밍을 위한 Redis Streams 이벤트 발행.

Event Types:
- stage: 파이프라인 단계 진행 상황 (intent, rag, answer 등)
- token: LLM 응답 토큰 스트리밍 (SSE delta)
- needs_input: 사용자 추가 입력 요청 (Human-in-the-Loop)

Port: application/ports/events/progress_notifier.py
"""

from __future__ import annotations

import json
import logging
import time
from typing import TYPE_CHECKING, Any

from chat_worker.application.ports.events.progress_notifier import ProgressNotifierPort

if TYPE_CHECKING:
    from redis.asyncio import Redis

logger = logging.getLogger(__name__)


class RedisProgressNotifier(ProgressNotifierPort):
    """Redis Streams 기반 진행률 알림.

    Redis Streams → event_router → Redis Pub/Sub → SSE Gateway → Frontend
    """

    def __init__(
        self,
        redis: "Redis",
        stream_prefix: str = "chat:events",
        maxlen: int = 1000,
    ):
        """초기화.

        Args:
            redis: Redis 클라이언트
            stream_prefix: 스트림 키 프리픽스
            maxlen: 스트림 최대 길이 (오래된 메시지 자동 삭제)
        """
        self._redis = redis
        self._stream_prefix = stream_prefix
        self._maxlen = maxlen
        logger.info(
            "RedisProgressNotifier initialized",
            extra={"prefix": stream_prefix, "maxlen": maxlen},
        )

    def _stream_key(self, task_id: str) -> str:
        """스트림 키 생성."""
        return f"{self._stream_prefix}:{task_id}"

    async def notify_stage(
        self,
        task_id: str,
        stage: str,
        status: str,
        progress: int | None = None,
        result: dict[str, Any] | None = None,
        message: str | None = None,
    ) -> str:
        """단계 이벤트 발행."""
        event_data = {
            "event_type": "stage",
            "task_id": task_id,
            "stage": stage,
            "status": status,
            "timestamp": time.time(),
        }
        if progress is not None:
            event_data["progress"] = progress
        if result is not None:
            event_data["result"] = json.dumps(result, ensure_ascii=False)
        if message is not None:
            event_data["message"] = message

        stream_key = self._stream_key(task_id)
        message_id = await self._redis.xadd(
            stream_key,
            event_data,
            maxlen=self._maxlen,
        )

        logger.debug(
            "Stage event published",
            extra={"task_id": task_id, "stage": stage, "status": status},
        )
        return message_id.decode() if isinstance(message_id, bytes) else str(message_id)

    async def notify_token(
        self,
        task_id: str,
        content: str,
    ) -> str:
        """토큰 스트리밍 이벤트 발행."""
        event_data = {
            "event_type": "token",
            "task_id": task_id,
            "content": content,
            "timestamp": time.time(),
        }

        stream_key = self._stream_key(task_id)
        message_id = await self._redis.xadd(
            stream_key,
            event_data,
            maxlen=self._maxlen,
        )
        return message_id.decode() if isinstance(message_id, bytes) else str(message_id)

    async def notify_needs_input(
        self,
        task_id: str,
        input_type: str,
        message: str,
        timeout: int = 60,
    ) -> str:
        """Human-in-the-Loop 입력 요청 이벤트 발행.

        Frontend가 이 이벤트를 수신하면:
        1. 권한 요청 UI 표시
        2. 사용자 입력 수집
        3. POST /chat/{job_id}/input으로 전송
        """
        event_data = {
            "event_type": "needs_input",
            "task_id": task_id,
            "input_type": input_type,
            "message": message,
            "timeout": str(timeout),
            "timestamp": time.time(),
        }

        stream_key = self._stream_key(task_id)
        message_id = await self._redis.xadd(
            stream_key,
            event_data,
            maxlen=self._maxlen,
        )

        logger.info(
            "needs_input event published",
            extra={
                "task_id": task_id,
                "input_type": input_type,
                "timeout": timeout,
            },
        )
        return message_id.decode() if isinstance(message_id, bytes) else str(message_id)
