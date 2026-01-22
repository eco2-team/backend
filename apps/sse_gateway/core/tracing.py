"""
OpenTelemetry Distributed Tracing Configuration for SSE Gateway

SSE Gateway 특화 분산 트레이싱:
- SSE 연결 수명 추적
- Redis Pub/Sub 구독 추적
- State 복구 추적

Architecture:
  SSE Gateway (OTel SDK) → OTLP/HTTP (4318) → Jaeger Collector → Elasticsearch
"""

import logging
import os
from contextlib import contextmanager
from typing import Any, Optional

from fastapi import FastAPI

logger = logging.getLogger(__name__)

# Environment variables
OTEL_EXPORTER_ENDPOINT = os.getenv(
    "OTEL_EXPORTER_OTLP_ENDPOINT",
    "http://jaeger-collector-clusterip.istio-system.svc.cluster.local:4318",
)
OTEL_EXPORTER_PROTOCOL = os.getenv("OTEL_EXPORTER_OTLP_PROTOCOL", "http/protobuf")
OTEL_SAMPLING_RATE = float(os.getenv("OTEL_SAMPLING_RATE", "0.1"))
OTEL_ENABLED = os.getenv("OTEL_ENABLED", "true").lower() == "true"

# Service constants
SERVICE_NAME = "sse-gateway"
SERVICE_VERSION = os.getenv("SERVICE_VERSION", "1.0.0")
ENVIRONMENT = os.getenv("ENVIRONMENT", "dev")

# Lazy imports to avoid overhead when tracing is disabled
_tracer_provider = None
_tracer = None


def configure_tracing() -> bool:
    """
    OpenTelemetry 트레이싱 설정

    Returns:
        bool: 설정 성공 여부
    """
    global _tracer_provider, _tracer

    if not OTEL_ENABLED:
        logger.info("OpenTelemetry tracing disabled (OTEL_ENABLED=false)")
        return False

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter,
        )
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.sdk.trace.sampling import TraceIdRatioBased

        # Resource attributes (ECS/OTel semantic conventions)
        resource = Resource.create(
            {
                "service.name": SERVICE_NAME,
                "service.version": SERVICE_VERSION,
                "deployment.environment": ENVIRONMENT,
                "telemetry.sdk.name": "opentelemetry",
                "telemetry.sdk.language": "python",
                # SSE Gateway 특화 속성
                "http.flavor": "1.1",
                "rpc.system": "sse",
            }
        )

        # Sampler (SSE는 장시간 연결이므로 낮은 샘플링)
        sampler = TraceIdRatioBased(OTEL_SAMPLING_RATE)

        # TracerProvider
        _tracer_provider = TracerProvider(
            resource=resource,
            sampler=sampler,
        )

        # OTLP HTTP Exporter (Jaeger Collector - 4318)
        # HTTP/protobuf는 gRPC보다 Istio mTLS와 호환성이 좋음
        exporter = OTLPSpanExporter(
            endpoint=f"{OTEL_EXPORTER_ENDPOINT}/v1/traces",
        )

        # BatchSpanProcessor (async, low overhead)
        _tracer_provider.add_span_processor(
            BatchSpanProcessor(
                exporter,
                max_queue_size=2048,
                max_export_batch_size=512,
                schedule_delay_millis=1000,
            )
        )

        trace.set_tracer_provider(_tracer_provider)
        _tracer = trace.get_tracer(SERVICE_NAME, SERVICE_VERSION)

        logger.info(
            "OpenTelemetry tracing configured",
            extra={
                "service": SERVICE_NAME,
                "endpoint": OTEL_EXPORTER_ENDPOINT,
                "sampling_rate": OTEL_SAMPLING_RATE,
            },
        )
        return True

    except ImportError as e:
        logger.warning(f"OpenTelemetry not available: {e}")
        return False
    except Exception as e:
        logger.error(f"Failed to configure tracing: {e}")
        return False


def instrument_fastapi(app: FastAPI) -> None:
    """
    FastAPI 자동 계측 (Auto-instrumentation)

    계측 항목:
    - HTTP 요청/응답 span
    - 요청 헤더에서 trace context 추출
    - 에러 자동 기록
    """
    if not OTEL_ENABLED:
        return

    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor.instrument_app(
            app,
            excluded_urls="health,ready,metrics,ping",  # Health check 제외
        )
        logger.info("FastAPI instrumentation enabled")

    except ImportError:
        logger.warning("FastAPIInstrumentor not available")
    except Exception as e:
        logger.error(f"Failed to instrument FastAPI: {e}")


def instrument_redis() -> None:
    """Redis 자동 계측 (Pub/Sub 구독 추적)"""
    if not OTEL_ENABLED:
        return

    try:
        from opentelemetry.instrumentation.redis import RedisInstrumentor

        RedisInstrumentor().instrument()
        logger.info("Redis instrumentation enabled")

    except ImportError:
        logger.warning("RedisInstrumentor not available")
    except Exception as e:
        logger.error(f"Failed to instrument Redis: {e}")


def shutdown_tracing() -> None:
    """트레이싱 종료 (graceful shutdown)"""
    global _tracer_provider

    if _tracer_provider is not None:
        try:
            _tracer_provider.shutdown()
            logger.info("OpenTelemetry tracing shutdown complete")
        except Exception as e:
            logger.error(f"Error shutting down tracing: {e}")


def get_tracer(name: str = SERVICE_NAME):
    """
    Tracer 인스턴스 반환 (수동 span 생성용)

    Usage:
        tracer = get_tracer()
        with tracer.start_as_current_span("sse_stream") as span:
            span.set_attribute("job_id", job_id)
    """
    global _tracer

    if not OTEL_ENABLED or _tracer is None:
        return None

    return _tracer


@contextmanager
def trace_sse_connection(job_id: str, attributes: Optional[dict[str, Any]] = None):
    """
    SSE 연결 수명 추적

    Usage:
        with trace_sse_connection(job_id) as span:
            async for event in manager.subscribe(job_id):
                if span:
                    span.add_event("event_sent", {"stage": event.stage})
                yield event
    """
    tracer = get_tracer()
    if tracer is None:
        yield None
        return

    with tracer.start_as_current_span(
        "sse.stream",
        attributes={
            "job.id": job_id,
            "messaging.system": "sse",
            "messaging.operation": "receive",
            **(attributes or {}),
        },
    ) as span:
        try:
            yield span
        except Exception as e:
            if span:
                from opentelemetry.trace import StatusCode

                span.set_status(StatusCode.ERROR, str(e))
                span.record_exception(e)
            raise


@contextmanager
def trace_pubsub_subscribe(job_id: str, channel: str):
    """
    Pub/Sub 구독 추적

    Usage:
        with trace_pubsub_subscribe(job_id, channel) as span:
            async for msg in pubsub.listen():
                process(msg)
    """
    tracer = get_tracer()
    if tracer is None:
        yield None
        return

    with tracer.start_as_current_span(
        "redis.subscribe",
        attributes={
            "db.system": "redis",
            "db.operation": "SUBSCRIBE",
            "messaging.destination.name": channel,
            "job.id": job_id,
        },
    ) as span:
        yield span


@contextmanager
def trace_state_recovery(job_id: str, state_key: str):
    """
    State 복구 추적

    Usage:
        with trace_state_recovery(job_id, state_key) as span:
            state = await redis.get(state_key)
            if span and state:
                span.set_attribute("state.found", True)
    """
    tracer = get_tracer()
    if tracer is None:
        yield None
        return

    with tracer.start_as_current_span(
        "redis.get_state",
        attributes={
            "db.system": "redis",
            "db.operation": "GET",
            "db.key": state_key,
            "job.id": job_id,
        },
    ) as span:
        yield span


@contextmanager
def trace_event_dispatch(job_id: str, stage: str, seq: int):
    """
    이벤트 디스패치 추적

    Usage:
        with trace_event_dispatch(job_id, stage, seq) as span:
            await queue.put(event)
    """
    tracer = get_tracer()
    if tracer is None:
        yield None
        return

    with tracer.start_as_current_span(
        f"sse.dispatch.{stage}",
        attributes={
            "job.id": job_id,
            "event.stage": stage,
            "event.seq": seq,
        },
    ) as span:
        yield span
