"""Redis Input Requester - InputRequesterPort 구현체.

needs_input 이벤트 발행만 담당.
상태 저장/조회는 InteractionStateStorePort에서 처리 (SoT 분리).

흐름:
1. Worker가 needs_input 이벤트 발행 (이 클래스)
2. Frontend가 이벤트 수신 후 입력 수집
3. Frontend가 POST /chat/{job_id}/input
4. API가 상태 복원 후 파이프라인 재개

Port: application/interaction/ports/input_requester.py
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from chat_worker.application.ports.input_requester import InputRequesterPort

if TYPE_CHECKING:
    from redis.asyncio import Redis

    from chat_worker.domain import InputType

logger = logging.getLogger(__name__)


class RedisInputRequester(InputRequesterPort):
    """Redis Streams 기반 입력 요청 발행.

    needs_input 이벤트만 발행합니다.
    상태 저장/조회는 RedisInteractionStateStore에서 처리.
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
            stream_prefix: 이벤트 스트림 프리픽스
            maxlen: 스트림 최대 길이
        """
        self._redis = redis
        self._stream_prefix = stream_prefix
        self._maxlen = maxlen

    def _stream_key(self, job_id: str) -> str:
        """스트림 키 생성."""
        return f"{self._stream_prefix}:{job_id}"

    async def request_input(
        self,
        job_id: str,
        input_type: "InputType",
        message: str,
        timeout: int = 60,
    ) -> str:
        """사용자 입력 요청 발행.

        needs_input 이벤트를 Redis Streams에 발행합니다.

        Args:
            job_id: 작업 ID
            input_type: 입력 타입 (location, confirmation 등)
            message: 사용자에게 표시할 메시지
            timeout: 입력 대기 시간 (초)

        Returns:
            이벤트 ID (요청 ID로 사용)
        """
        event_data = {
            "event_type": "needs_input",
            "task_id": job_id,
            "input_type": input_type.value,
            "message": message,
            "timeout": str(timeout),
            "timestamp": time.time(),
        }

        stream_key = self._stream_key(job_id)
        message_id = await self._redis.xadd(
            stream_key,
            event_data,
            maxlen=self._maxlen,
        )

        request_id = message_id.decode() if isinstance(message_id, bytes) else str(message_id)

        logger.info(
            "Input request event published",
            extra={
                "job_id": job_id,
                "input_type": input_type.value,
                "request_id": request_id,
                "timeout": timeout,
            },
        )

        return request_id
