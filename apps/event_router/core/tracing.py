"""
OpenTelemetry Distributed Tracing Configuration for Event Router

Event Router 특화 분산 트레이싱:
- Redis Streams 이벤트 처리 추적
- Consumer Group 상태 추적
- Pub/Sub 발행 추적

Architecture:
  Event Router (OTel SDK) → OTLP/HTTP (4318) → Jaeger Collector → Elasticsearch
"""

import logging
import os
from contextlib import contextmanager
from typing import Any, Optional

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
SERVICE_NAME = "event-router"
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
                # Event Router 특화 속성
                "messaging.system": "redis",
                "messaging.destination.kind": "stream",
            }
        )

        # Sampler (production: 10%, dev: 100%)
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


def instrument_redis() -> None:
    """Redis 자동 계측 (Streams/Pub/Sub 명령 추적)"""
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
        with tracer.start_as_current_span("process_event") as span:
            span.set_attribute("job_id", job_id)
    """
    global _tracer

    if not OTEL_ENABLED or _tracer is None:
        return None

    return _tracer


@contextmanager
def trace_event_processing(
    job_id: str,
    stage: str,
    shard: int,
    msg_id: str,
    attributes: Optional[dict[str, Any]] = None,
):
    """
    이벤트 처리 트레이싱 컨텍스트 매니저

    Usage:
        with trace_event_processing(job_id, stage, shard, msg_id) as span:
            # 이벤트 처리 로직
            if span:
                span.add_event("published_to_pubsub")
    """
    tracer = get_tracer()
    if tracer is None:
        yield None
        return

    with tracer.start_as_current_span(
        f"event_router.process.{stage}",
        attributes={
            "job.id": job_id,
            "event.stage": stage,
            "messaging.destination.name": f"scan:events:{shard}",
            "messaging.message.id": msg_id,
            **(attributes or {}),
        },
    ) as span:
        try:
            yield span
        except Exception as e:
            if span:
                span.set_status(
                    __import__("opentelemetry.trace", fromlist=["StatusCode"]).StatusCode.ERROR,
                    str(e),
                )
                span.record_exception(e)
            raise


@contextmanager
def trace_xreadgroup(
    stream_keys: list[str],
    consumer_group: str,
    consumer_name: str,
):
    """
    XREADGROUP 작업 트레이싱

    Usage:
        with trace_xreadgroup(stream_keys, group, consumer) as span:
            events = await redis.xreadgroup(...)
    """
    tracer = get_tracer()
    if tracer is None:
        yield None
        return

    with tracer.start_as_current_span(
        "redis.xreadgroup",
        attributes={
            "db.system": "redis",
            "db.operation": "XREADGROUP",
            "messaging.consumer.group.name": consumer_group,
            "messaging.consumer.name": consumer_name,
            "messaging.destination.name": ",".join(stream_keys),
        },
    ) as span:
        yield span


@contextmanager
def trace_publish(job_id: str, channel: str, stage: str):
    """
    Pub/Sub PUBLISH 작업 트레이싱

    Usage:
        with trace_publish(job_id, channel, stage) as span:
            await redis.publish(channel, data)
    """
    tracer = get_tracer()
    if tracer is None:
        yield None
        return

    with tracer.start_as_current_span(
        "redis.publish",
        attributes={
            "db.system": "redis",
            "db.operation": "PUBLISH",
            "messaging.destination.name": channel,
            "job.id": job_id,
            "event.stage": stage,
        },
    ) as span:
        yield span


@contextmanager
def trace_reclaim(stream_key: str, min_idle_ms: int):
    """
    XAUTOCLAIM 작업 트레이싱

    Usage:
        with trace_reclaim(stream_key, min_idle_ms) as span:
            result = await redis.xautoclaim(...)
    """
    tracer = get_tracer()
    if tracer is None:
        yield None
        return

    with tracer.start_as_current_span(
        "redis.xautoclaim",
        attributes={
            "db.system": "redis",
            "db.operation": "XAUTOCLAIM",
            "messaging.destination.name": stream_key,
            "reclaim.min_idle_ms": min_idle_ms,
        },
    ) as span:
        yield span
