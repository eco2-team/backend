"""Event Consumer Port.

메시지 큐 소비자 인터페이스입니다.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Protocol


class EventConsumer(Protocol):
    """이벤트 소비자 인터페이스.

    구현체:
        - RabbitMQConsumer (infrastructure/messaging/)
    """

    async def start(
        self,
        handler: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None:
        """이벤트 소비 시작.

        Args:
            handler: 이벤트 핸들러 콜백
        """
        ...

    async def stop(self) -> None:
        """이벤트 소비 중지."""
        ...
