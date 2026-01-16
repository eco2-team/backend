"""Tracer - OpenTelemetry 분산 추적 유틸리티.

ADR P2 요구사항:
- 각 노드에 span 추가
- 표준 속성: intent, user_id, latency_ms, status

환경 변수:
- OTEL_SERVICE_NAME: 서비스 이름 (기본: chat-worker)
- OTEL_ENABLED: 추적 활성화 (기본: false)
"""

from __future__ import annotations

import functools
import logging
import os
import time
from typing import TYPE_CHECKING, Any, Callable, Coroutine, TypeVar

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.trace import Span, Status, StatusCode

if TYPE_CHECKING:
    from opentelemetry.trace import Tracer

logger = logging.getLogger(__name__)

# 환경 변수
OTEL_SERVICE_NAME = os.getenv("OTEL_SERVICE_NAME", "chat-worker")
OTEL_ENABLED = os.getenv("OTEL_ENABLED", "false").lower() == "true"

# 타입 변수
T = TypeVar("T")


def _setup_tracer() -> "Tracer":
    """TracerProvider 설정 및 Tracer 반환.

    Note:
        Production에서는 OTLP Exporter 설정 필요.
        (opentelemetry-exporter-otlp 패키지)

    Returns:
        설정된 Tracer 인스턴스
    """
    if not trace.get_tracer_provider():
        # 기본 TracerProvider 설정 (로컬 개발용)
        provider = TracerProvider()
        trace.set_tracer_provider(provider)
        logger.info(
            "OpenTelemetry TracerProvider initialized",
            extra={"service_name": OTEL_SERVICE_NAME, "enabled": OTEL_ENABLED},
        )

    return trace.get_tracer(OTEL_SERVICE_NAME)


# 싱글톤 Tracer
_tracer: "Tracer | None" = None


def get_tracer() -> "Tracer":
    """Tracer 싱글톤 반환.

    Returns:
        OpenTelemetry Tracer 인스턴스
    """
    global _tracer
    if _tracer is None:
        _tracer = _setup_tracer()
    return _tracer


def set_span_attributes(span: Span, attributes: dict[str, Any]) -> None:
    """Span에 속성 일괄 설정.

    None 값은 무시됩니다.

    Args:
        span: OpenTelemetry Span
        attributes: 설정할 속성 딕셔너리

    Example:
        >>> span = trace.get_current_span()
        >>> set_span_attributes(span, {
        ...     "intent": "waste",
        ...     "user_id": "user-123",
        ...     "latency_ms": 150.5,
        ... })
    """
    for key, value in attributes.items():
        if value is not None:
            # OpenTelemetry는 기본 타입만 지원
            if isinstance(value, (str, bool, int, float)):
                span.set_attribute(key, value)
            else:
                span.set_attribute(key, str(value))


# 노드 함수 타입
NodeFunc = Callable[[dict[str, Any]], Coroutine[Any, Any, dict[str, Any]]]


def with_span(
    span_name: str,
    extract_attributes: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
):
    """노드에 OpenTelemetry span을 추가하는 데코레이터.

    ADR P2 패턴:
    - 시작 시: intent, user_id, job_id 기록
    - 종료 시: latency_ms, status 기록

    Args:
        span_name: Span 이름 (예: "waste_rag_node")
        extract_attributes: state에서 추가 속성 추출 함수

    Returns:
        데코레이터

    Example:
        ```python
        @with_span("waste_rag_node")
        async def waste_rag_node(state: dict[str, Any]) -> dict[str, Any]:
            ...
        ```
    """

    def decorator(func: NodeFunc) -> NodeFunc:
        @functools.wraps(func)
        async def wrapper(state: dict[str, Any]) -> dict[str, Any]:
            if not OTEL_ENABLED:
                # 추적 비활성화 시 바로 실행
                return await func(state)

            tracer = get_tracer()
            start_time = time.time()

            with tracer.start_as_current_span(span_name) as span:
                # 시작 속성 기록
                set_span_attributes(
                    span,
                    {
                        "intent": state.get("intent"),
                        "user_id": state.get("user_id"),
                        "job_id": state.get("job_id"),
                    },
                )

                # 추가 속성 추출
                if extract_attributes:
                    extra = extract_attributes(state)
                    set_span_attributes(span, extra)

                try:
                    result = await func(state)

                    # 성공 시 속성 기록
                    latency_ms = (time.time() - start_time) * 1000
                    set_span_attributes(
                        span,
                        {
                            "latency_ms": latency_ms,
                            "status": "success",
                        },
                    )
                    span.set_status(Status(StatusCode.OK))

                    return result

                except Exception as e:
                    # 실패 시 속성 기록
                    latency_ms = (time.time() - start_time) * 1000
                    set_span_attributes(
                        span,
                        {
                            "latency_ms": latency_ms,
                            "status": "error",
                            "error_type": type(e).__name__,
                            "error_message": str(e),
                        },
                    )
                    span.set_status(Status(StatusCode.ERROR, str(e)))
                    span.record_exception(e)
                    raise

        return wrapper

    return decorator


__all__ = [
    "OTEL_ENABLED",
    "OTEL_SERVICE_NAME",
    "get_tracer",
    "set_span_attributes",
    "with_span",
]
