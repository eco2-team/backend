"""Prometheus Metrics Adapter - MetricsPort 구현.

Infrastructure Layer에서 MetricsPort를 Prometheus로 구현합니다.
Application Layer는 Prometheus를 직접 알지 않고 MetricsPort만 사용.

metrics.py의 Prometheus 메트릭을 활용하며,
MetricsPort 인터페이스를 통해 Application Layer에서 사용 가능하게 합니다.
"""

from __future__ import annotations

import logging

from chat_worker.application.ports.metrics import MetricsPort
from chat_worker.infrastructure.metrics.metrics import (
    CHAT_REQUESTS_TOTAL,
    CHAT_REQUEST_DURATION,
    CHAT_ERRORS_TOTAL,
    CHAT_INTENT_DISTRIBUTION,
    CHAT_SUBAGENT_CALLS,
    CHAT_SUBAGENT_DURATION,
)

logger = logging.getLogger(__name__)


class PrometheusMetricsAdapter(MetricsPort):
    """Prometheus 메트릭 어댑터.

    MetricsPort를 Prometheus로 구현합니다.
    Application Layer에서는 MetricsPort 타입으로만 주입받습니다.

    사용 예시:
        metrics = PrometheusMetricsAdapter()
        metrics.track_request(
            intent="waste",
            status="success",
            provider="openai",
            duration=1.5,
        )
    """

    def track_request(
        self,
        intent: str,
        status: str,
        provider: str,
        duration: float,
    ) -> None:
        """요청 메트릭 기록."""
        try:
            CHAT_REQUESTS_TOTAL.labels(
                intent=intent,
                status=status,
                provider=provider,
            ).inc()
            CHAT_REQUEST_DURATION.labels(
                intent=intent,
                provider=provider,
            ).observe(duration)
        except Exception as e:
            logger.warning(
                "metrics_track_request_failed",
                extra={"error": str(e)},
            )

    def track_intent(self, intent: str) -> None:
        """Intent 분류 메트릭 기록."""
        try:
            CHAT_INTENT_DISTRIBUTION.labels(intent=intent).inc()
        except Exception as e:
            logger.warning(
                "metrics_track_intent_failed",
                extra={"intent": intent, "error": str(e)},
            )

    def track_error(self, intent: str, error_type: str) -> None:
        """에러 메트릭 기록."""
        try:
            CHAT_ERRORS_TOTAL.labels(
                intent=intent,
                error_type=error_type,
            ).inc()
        except Exception as e:
            logger.warning(
                "metrics_track_error_failed",
                extra={"intent": intent, "error_type": error_type, "error": str(e)},
            )

    def track_cache_hit(self, cache_type: str) -> None:
        """캐시 히트 메트릭 기록.

        TODO: 별도 캐시 메트릭 Counter 추가 시 구현
        """
        logger.debug("cache_hit", extra={"cache_type": cache_type})

    def track_cache_miss(self, cache_type: str) -> None:
        """캐시 미스 메트릭 기록.

        TODO: 별도 캐시 메트릭 Counter 추가 시 구현
        """
        logger.debug("cache_miss", extra={"cache_type": cache_type})

    def track_subagent_call(
        self,
        subagent: str,
        status: str,
        duration: float,
    ) -> None:
        """서브에이전트 호출 메트릭 기록."""
        try:
            CHAT_SUBAGENT_CALLS.labels(
                subagent=subagent,
                status=status,
            ).inc()
            CHAT_SUBAGENT_DURATION.labels(
                subagent=subagent,
            ).observe(duration)
        except Exception as e:
            logger.warning(
                "metrics_track_subagent_failed",
                extra={"subagent": subagent, "error": str(e)},
            )


class NoOpMetricsAdapter(MetricsPort):
    """NoOp 메트릭 어댑터.

    테스트 환경이나 메트릭 비활성화 시 사용.
    모든 메서드가 아무 것도 하지 않습니다.
    """

    def track_request(
        self,
        intent: str,
        status: str,
        provider: str,
        duration: float,
    ) -> None:
        """NoOp."""
        pass

    def track_intent(self, intent: str) -> None:
        """NoOp."""
        pass

    def track_error(self, intent: str, error_type: str) -> None:
        """NoOp."""
        pass
