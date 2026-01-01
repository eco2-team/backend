"""EventPublisher Port.

이벤트를 메시지 큐로 발행하는 인터페이스입니다.
"""

from __future__ import annotations

from typing import Protocol


class EventPublisher(Protocol):
    """이벤트 발행 인터페이스.

    구현체:
        - RabbitMQEventPublisher (infrastructure/messaging/)
    """

    async def publish(self, event_json: str) -> None:
        """이벤트 발행.

        Args:
            event_json: 이벤트 JSON 문자열

        Raises:
            PublishError: 발행 실패 시
        """
        ...

    async def connect(self) -> None:
        """연결 수립."""
        ...

    async def close(self) -> None:
        """연결 종료."""
        ...
