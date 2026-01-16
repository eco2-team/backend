"""Celery Default Character Publisher Implementation.

character.grant_default 큐로 이벤트를 발행합니다.
character_worker가 이벤트를 수신하여 기본 캐릭터를 지급합니다.

분산 트레이싱 통합:
- API 요청의 trace context를 Celery headers로 전파
- Worker가 headers에서 trace context를 복원하여 child span 생성
"""

import logging
import os
from uuid import UUID

from celery import Celery

from users.application.character.ports import DefaultCharacterPublisher

logger = logging.getLogger(__name__)

# OpenTelemetry 활성화 여부
OTEL_ENABLED = os.getenv("OTEL_ENABLED", "true").lower() == "true"
TRACEPARENT_HEADER = "traceparent"


def _get_trace_headers() -> dict[str, str]:
    """현재 trace context를 Celery headers로 추출."""
    if not OTEL_ENABLED:
        return {}

    try:
        from opentelemetry import trace
        from opentelemetry.trace import format_trace_id, format_span_id

        current_span = trace.get_current_span()
        span_context = current_span.get_span_context()

        if span_context.is_valid:
            trace_id = format_trace_id(span_context.trace_id)
            span_id = format_span_id(span_context.span_id)
            trace_flags = f"{span_context.trace_flags:02x}"
            traceparent = f"00-{trace_id}-{span_id}-{trace_flags}"
            return {TRACEPARENT_HEADER: traceparent}
    except ImportError:
        pass
    except Exception as e:
        logger.debug(f"Failed to get trace context: {e}")

    return {}


class CeleryDefaultCharacterPublisher(DefaultCharacterPublisher):
    """Celery 기반 기본 캐릭터 발행자.

    character.grant_default 태스크를 호출합니다.
    """

    def __init__(self, celery_app: Celery) -> None:
        """Initialize.

        Args:
            celery_app: Celery 앱 인스턴스
        """
        self._celery_app = celery_app

    def publish(self, user_id: UUID) -> None:
        """기본 캐릭터 지급 이벤트를 발행합니다.

        ⚠️ exchange="" = AMQP default exchange (routing_key와 동일한 이름의 큐로 직접 전달)
        - queue= 사용 시 Celery가 큐를 auto-declare하여 Topology CR과 충돌
        - 'celery' exchange는 topic 타입이라 direct 선언 시 충돌
        """
        try:
            # Trace context를 Celery headers로 전파
            headers = _get_trace_headers()
            self._celery_app.send_task(
                "character.grant_default",
                kwargs={"user_id": str(user_id)},
                exchange="",
                routing_key="character.grant_default",
                headers=headers,
            )
            logger.info(
                "Default character grant event published",
                extra={"user_id": str(user_id)},
            )
        except Exception:
            logger.exception(
                "Failed to publish default character grant event",
                extra={"user_id": str(user_id)},
            )
            # Fire-and-forget: 실패해도 예외 전파 안 함
