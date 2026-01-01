"""Relay Event Command.

Outbox 이벤트를 RabbitMQ로 재발행하는 Use Case입니다.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from apps.auth_relay.application.common.result import RelayResult

if TYPE_CHECKING:
    from apps.auth_relay.application.common.ports.event_publisher import EventPublisher

logger = logging.getLogger(__name__)


class RelayEventCommand:
    """이벤트 재발행 Command.

    Clean Architecture의 Use Case에 해당합니다.
    Outbox 이벤트를 RabbitMQ로 발행하는 단일 책임을 가집니다.
    """

    def __init__(self, publisher: "EventPublisher") -> None:
        """Initialize.

        Args:
            publisher: 이벤트 발행자 (DI)
        """
        self._publisher = publisher

    async def execute(self, event_json: str) -> RelayResult:
        """이벤트 재발행 처리.

        Args:
            event_json: 이벤트 JSON 문자열

        Returns:
            RelayResult: 실행 결과 (SUCCESS/RETRYABLE/DROP)
        """
        # 1. JSON 유효성 검증
        try:
            event = json.loads(event_json)
            jti = event.get("jti", "")[:8]
        except json.JSONDecodeError as e:
            logger.error("Invalid JSON in outbox", extra={"error": str(e)})
            return RelayResult.drop(f"Invalid JSON: {e}")

        # 2. 발행 시도
        try:
            await self._publisher.publish(event_json)
            logger.debug("Event relayed", extra={"jti": jti})
            return RelayResult.success()

        except (ConnectionError, TimeoutError, OSError) as e:
            # 일시적 실패 → 재시도 가능
            logger.warning(
                "Temporary failure, will retry",
                extra={"error": str(e), "jti": jti},
            )
            return RelayResult.retryable(str(e))

        except Exception as e:
            # 예상치 못한 오류 → DLQ
            logger.exception("Unexpected error, moving to DLQ")
            return RelayResult.drop(str(e))
