"""OutboxReader Port.

Outbox에서 이벤트를 읽는 인터페이스입니다.
"""

from __future__ import annotations

from typing import Protocol


class OutboxReader(Protocol):
    """Outbox 읽기 인터페이스.

    구현체:
        - RedisOutboxReader (infrastructure/persistence_redis/)
    """

    async def pop(self) -> str | None:
        """Outbox에서 이벤트 꺼내기 (RPOP).

        Returns:
            이벤트 JSON 문자열 또는 None
        """
        ...

    async def push_back(self, data: str) -> None:
        """이벤트를 Outbox 앞에 다시 넣기 (LPUSH).

        Args:
            data: 이벤트 JSON 문자열
        """
        ...

    async def push_to_dlq(self, data: str) -> None:
        """이벤트를 DLQ로 이동.

        Args:
            data: 이벤트 JSON 문자열
        """
        ...

    async def length(self) -> int:
        """Outbox 큐 길이 조회.

        Returns:
            큐 길이
        """
        ...
