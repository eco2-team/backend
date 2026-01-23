"""Dead Letter Queue Handler - 실패 메시지 처리.

DLQ 역할:
- 재시도 실패 메시지 저장
- 수동 재처리 지원
- 실패 원인 분석

저장소:
- Redis Stream: chat:dlq
- TTL: 7일
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from redis.asyncio import Redis

logger = logging.getLogger(__name__)

DLQ_STREAM_KEY = "chat:dlq"
DLQ_TTL = 7 * 24 * 60 * 60  # 7일
DLQ_MAXLEN = 10000


@dataclass
class DeadLetterMessage:
    """Dead Letter 메시지."""

    job_id: str
    session_id: str
    user_id: str
    message: str
    error: str
    error_type: str
    retry_count: int
    failed_at: str
    original_payload: dict[str, Any]

    @classmethod
    def from_dict(cls, data: dict) -> "DeadLetterMessage":
        return cls(**data)

    def to_dict(self) -> dict:
        return asdict(self)


class DLQHandler:
    """Dead Letter Queue Handler.

    실패 메시지를 저장하고 재처리를 지원합니다.
    """

    def __init__(
        self,
        redis: "Redis",
        stream_key: str = DLQ_STREAM_KEY,
        maxlen: int = DLQ_MAXLEN,
    ):
        """초기화.

        Args:
            redis: Redis 클라이언트
            stream_key: DLQ 스트림 키
            maxlen: 최대 메시지 수
        """
        self._redis = redis
        self._stream_key = stream_key
        self._maxlen = maxlen

    async def push(
        self,
        job_id: str,
        session_id: str,
        user_id: str,
        message: str,
        error: Exception,
        retry_count: int = 0,
        original_payload: dict[str, Any] | None = None,
    ) -> str:
        """실패 메시지를 DLQ에 추가.

        Args:
            job_id: 작업 ID
            session_id: 세션 ID
            user_id: 사용자 ID
            message: 원본 메시지
            error: 발생한 예외
            retry_count: 재시도 횟수
            original_payload: 원본 페이로드

        Returns:
            DLQ 메시지 ID
        """
        dlq_message = DeadLetterMessage(
            job_id=job_id,
            session_id=session_id,
            user_id=user_id,
            message=message,
            error=str(error),
            error_type=type(error).__name__,
            retry_count=retry_count,
            failed_at=datetime.utcnow().isoformat(),
            original_payload=original_payload or {},
        )

        entry_id = await self._redis.xadd(
            self._stream_key,
            {"data": json.dumps(dlq_message.to_dict())},
            maxlen=self._maxlen,
        )

        logger.warning(
            "dlq_message_added",
            extra={
                "dlq_id": entry_id,
                "job_id": job_id,
                "error_type": dlq_message.error_type,
                "retry_count": retry_count,
            },
        )

        return entry_id

    async def pop(self) -> DeadLetterMessage | None:
        """DLQ에서 가장 오래된 메시지 꺼내기.

        Returns:
            DeadLetterMessage 또는 None
        """
        result = await self._redis.xrange(
            self._stream_key,
            count=1,
        )

        if not result:
            return None

        entry_id, data = result[0]
        message_data = json.loads(data.get("data", "{}"))

        # 메시지 삭제
        await self._redis.xdel(self._stream_key, entry_id)

        return DeadLetterMessage.from_dict(message_data)

    async def peek(self, count: int = 10) -> list[tuple[str, DeadLetterMessage]]:
        """DLQ 메시지 미리보기 (삭제하지 않음).

        Args:
            count: 조회할 메시지 수

        Returns:
            [(entry_id, DeadLetterMessage), ...]
        """
        result = await self._redis.xrange(
            self._stream_key,
            count=count,
        )

        messages = []
        for entry_id, data in result:
            message_data = json.loads(data.get("data", "{}"))
            messages.append((entry_id, DeadLetterMessage.from_dict(message_data)))

        return messages

    async def reprocess(self, entry_id: str) -> DeadLetterMessage | None:
        """특정 메시지 재처리를 위해 꺼내기.

        Args:
            entry_id: DLQ 메시지 ID

        Returns:
            DeadLetterMessage 또는 None
        """
        result = await self._redis.xrange(
            self._stream_key,
            min=entry_id,
            max=entry_id,
        )

        if not result:
            return None

        _, data = result[0]
        message_data = json.loads(data.get("data", "{}"))

        # 메시지 삭제
        await self._redis.xdel(self._stream_key, entry_id)

        logger.info(
            "dlq_message_reprocessed",
            extra={
                "dlq_id": entry_id,
                "job_id": message_data.get("job_id"),
            },
        )

        return DeadLetterMessage.from_dict(message_data)

    async def delete(self, entry_id: str) -> bool:
        """DLQ 메시지 삭제.

        Args:
            entry_id: DLQ 메시지 ID

        Returns:
            삭제 성공 여부
        """
        deleted = await self._redis.xdel(self._stream_key, entry_id)
        return deleted > 0

    async def count(self) -> int:
        """DLQ 메시지 수.

        Returns:
            메시지 수
        """
        return await self._redis.xlen(self._stream_key)

    async def clear(self) -> int:
        """DLQ 전체 삭제.

        Returns:
            삭제된 메시지 수
        """
        count = await self.count()
        await self._redis.unlink(self._stream_key)
        logger.info("dlq_cleared", extra={"deleted_count": count})
        return count

    async def get_stats(self) -> dict[str, Any]:
        """DLQ 통계.

        Returns:
            통계 정보
        """
        messages = await self.peek(count=1000)

        error_types: dict[str, int] = {}
        for _, msg in messages:
            error_types[msg.error_type] = error_types.get(msg.error_type, 0) + 1

        return {
            "total_messages": len(messages),
            "error_types": error_types,
            "stream_key": self._stream_key,
        }
