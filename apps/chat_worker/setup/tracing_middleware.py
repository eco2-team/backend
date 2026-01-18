"""OpenTelemetry Tracing Middleware for Taskiq.

Taskiq 메시지에서 W3C TraceContext를 추출하여
분산 트레이싱을 연결합니다.

API → MQ → Worker 간 trace context 전파:
1. Chat API가 traceparent를 메시지 labels에 주입
2. 이 미들웨어가 labels에서 traceparent 추출
3. 추출된 context를 parent로 하는 새 span 생성
4. Jaeger에서 전체 요청 흐름 추적 가능

사용법:
    broker.add_middlewares(TracingMiddleware())
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Any

from taskiq import TaskiqMiddleware, TaskiqMessage, TaskiqResult

if TYPE_CHECKING:
    from opentelemetry.trace import Span

logger = logging.getLogger(__name__)

OTEL_ENABLED = os.getenv("OTEL_ENABLED", "true").lower() == "true"


class TracingMiddleware(TaskiqMiddleware):
    """Taskiq OpenTelemetry 트레이싱 미들웨어.

    메시지 labels에서 W3C TraceContext 추출하여
    분산 트레이싱을 연결합니다.

    Span 생성:
    - pre_execute: parent context로 "taskiq.process" span 시작
    - post_execute: span 종료 및 상태 기록
    """

    def __init__(self):
        """초기화."""
        self._tracer = None
        # task_id → (context_token, span) 매핑
        # 동시 실행되는 태스크들을 안전하게 관리
        self._active_spans: dict[str, tuple[object, "Span"]] = {}

    def _get_tracer(self):
        """Tracer lazy 초기화."""
        if self._tracer is None and OTEL_ENABLED:
            try:
                from opentelemetry import trace

                self._tracer = trace.get_tracer(
                    "chat-worker.taskiq",
                    schema_url="https://opentelemetry.io/schemas/1.21.0",
                )
            except ImportError:
                pass
        return self._tracer

    def _extract_context(self, labels: dict[str, str]):
        """메시지 labels에서 trace context 추출.

        Args:
            labels: Taskiq 메시지 labels (traceparent, tracestate 포함)

        Returns:
            OpenTelemetry Context 또는 None
        """
        if not OTEL_ENABLED:
            return None

        traceparent = labels.get("traceparent")
        if not traceparent:
            return None

        try:
            from opentelemetry.trace.propagation.tracecontext import (
                TraceContextTextMapPropagator,
            )

            propagator = TraceContextTextMapPropagator()
            ctx = propagator.extract(carrier=labels)

            logger.debug(
                "Trace context extracted from message",
                extra={"traceparent": traceparent},
            )
            return ctx

        except Exception as e:
            logger.warning(f"Failed to extract trace context: {e}")
            return None

    async def pre_execute(self, message: TaskiqMessage) -> TaskiqMessage:
        """태스크 실행 전 trace context 설정 및 span 시작.

        메시지 labels에서 traceparent 추출하여:
        1. OpenTelemetry context 설정 (parent span 연결)
        2. "taskiq.process" span 시작 (Jaeger에 표시)
        """
        if not OTEL_ENABLED:
            return message

        tracer = self._get_tracer()
        if tracer is None:
            return message

        labels = message.labels or {}
        parent_ctx = self._extract_context(labels)

        try:
            from opentelemetry import context as otel_context
            from opentelemetry.trace import SpanKind, Status, StatusCode

            # Parent context가 있으면 attach, 없으면 새 trace 시작
            token = None
            if parent_ctx is not None:
                token = otel_context.attach(parent_ctx)

            # Span 시작 (Jaeger에 표시됨)
            span = tracer.start_span(
                name=f"taskiq.{message.task_name}",
                kind=SpanKind.CONSUMER,
                attributes={
                    "messaging.system": "rabbitmq",
                    "messaging.operation": "process",
                    "messaging.destination": "chat.process",
                    "taskiq.task_id": message.task_id,
                    "taskiq.task_name": message.task_name,
                },
            )

            # Span을 현재 context로 설정
            span_ctx = otel_context.set_value("current_span", span)
            span_token = otel_context.attach(span_ctx)

            # 정리를 위해 저장 (token, span, span_token)
            self._active_spans[message.task_id] = (token, span, span_token)

            logger.debug(
                "Trace span started",
                extra={
                    "task_id": message.task_id,
                    "task_name": message.task_name,
                    "traceparent": labels.get("traceparent"),
                },
            )

        except Exception as e:
            logger.warning(f"Failed to start trace span: {e}")

        return message

    async def post_execute(
        self,
        message: TaskiqMessage,
        result: TaskiqResult[Any],
    ) -> None:
        """태스크 실행 후 span 종료 및 context 정리.

        실행 결과에 따라 span 상태 설정:
        - 성공: Status.OK
        - 실패: Status.ERROR + 에러 정보 기록
        """
        if not OTEL_ENABLED:
            return

        if message.task_id not in self._active_spans:
            return

        try:
            from opentelemetry import context as otel_context
            from opentelemetry.trace import Status, StatusCode

            token, span, span_token = self._active_spans.pop(message.task_id)

            # 실행 결과에 따른 span 상태 설정
            if result.is_err:
                span.set_status(Status(StatusCode.ERROR, str(result.error)))
                span.set_attribute("error.type", type(result.error).__name__)
                span.record_exception(result.error)
            else:
                span.set_status(Status(StatusCode.OK))

            # Span 종료
            span.end()

            # Context 정리 (역순으로 detach)
            otel_context.detach(span_token)
            if token is not None:
                otel_context.detach(token)

            logger.debug(
                "Trace span ended",
                extra={
                    "task_id": message.task_id,
                    "is_error": result.is_err,
                },
            )

        except Exception as e:
            logger.warning(f"Failed to end trace span: {e}")

    async def on_error(
        self,
        message: TaskiqMessage,
        result: TaskiqResult[Any],
        exception: BaseException,
    ) -> None:
        """태스크 에러 발생 시 span에 예외 기록.

        post_execute보다 먼저 호출되어 예외 정보를 span에 기록합니다.
        """
        if not OTEL_ENABLED:
            return

        if message.task_id not in self._active_spans:
            return

        try:
            _, span, _ = self._active_spans[message.task_id]
            span.record_exception(exception)
            span.set_attribute("error.message", str(exception))

        except Exception as e:
            logger.warning(f"Failed to record exception in span: {e}")
