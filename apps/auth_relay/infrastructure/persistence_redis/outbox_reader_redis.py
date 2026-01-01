"""Redis Outbox Reader.

OutboxReader 포트의 Redis 구현체입니다.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from redis.asyncio import Redis as AsyncRedis

logger = logging.getLogger(__name__)


class RedisOutboxReader:
    """Redis 기반 Outbox Reader.

    OutboxReader 인터페이스 구현체입니다.
    FIFO 큐로 동작: LPUSH로 추가, RPOP으로 제거
    """

    OUTBOX_KEY = "outbox:blacklist"
    DLQ_KEY = "outbox:blacklist:dlq"

    def __init__(self, redis: "AsyncRedis") -> None:
        """Initialize.

        Args:
            redis: Redis 클라이언트
        """
        self._redis = redis

    async def pop(self) -> str | None:
        """Outbox에서 이벤트 꺼내기 (RPOP).

        Returns:
            이벤트 JSON 문자열 또는 None
        """
        result = await self._redis.rpop(self.OUTBOX_KEY)
        if result is None:
            return None
        return result if isinstance(result, str) else result.decode("utf-8")

    async def push_back(self, data: str) -> None:
        """이벤트를 Outbox 앞에 다시 넣기 (LPUSH).

        재시도를 위해 큐 앞에 다시 삽입합니다.

        Args:
            data: 이벤트 JSON 문자열
        """
        await self._redis.lpush(self.OUTBOX_KEY, data)
        logger.debug("Event pushed back to outbox")

    async def push_to_dlq(self, data: str) -> None:
        """이벤트를 DLQ로 이동.

        영구적 실패한 이벤트를 Dead Letter Queue로 이동합니다.

        Args:
            data: 이벤트 JSON 문자열
        """
        await self._redis.lpush(self.DLQ_KEY, data)
        logger.warning("Event moved to DLQ")

    async def length(self) -> int:
        """Outbox 큐 길이 조회.

        Returns:
            큐 길이
        """
        return await self._redis.llen(self.OUTBOX_KEY)
