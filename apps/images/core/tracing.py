"""
OpenTelemetry Distributed Tracing Configuration

CNCF/BigTech 베스트 프랙티스 기반 분산 트레이싱 설정:
- Google Dapper: Low overhead, application-level transparency
- Netflix Edgar: Request interceptor pattern, async collection
- Uber Jaeger: OpenTelemetry native, adaptive sampling

Architecture:
  App (OTel SDK) → OTLP/gRPC (4317) → Jaeger Collector → Elasticsearch
"""

import logging
import os
from typing import Optional

from fastapi import FastAPI

logger = logging.getLogger(__name__)

# Environment variables
OTEL_EXPORTER_ENDPOINT = os.getenv(
    "OTEL_EXPORTER_OTLP_ENDPOINT",
    "jaeger-collector.istio-system.svc.cluster.local:4317",
)
OTEL_SAMPLING_RATE = float(os.getenv("OTEL_SAMPLING_RATE", "1.0"))
OTEL_ENABLED = os.getenv("OTEL_ENABLED", "true").lower() == "true"

# Lazy imports to avoid overhead when tracing is disabled
_tracer_provider = None


def configure_tracing(
    service_name: str,
    service_version: str,
    environment: str = "dev",
) -> bool:
    """
    OpenTelemetry 트레이싱 설정

    Args:
        service_name: 서비스 이름 (e.g., "auth-api")
        service_version: 서비스 버전 (e.g., "1.0.7")
        environment: 환경 (dev/staging/prod)

    Returns:
        bool: 설정 성공 여부
    """
    global _tracer_provider

    if not OTEL_ENABLED:
        logger.info("OpenTelemetry tracing disabled (OTEL_ENABLED=false)")
        return False

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
            OTLPSpanExporter,
        )
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.sdk.trace.sampling import TraceIdRatioBased

        # Resource attributes (ECS/OTel semantic conventions)
        resource = Resource.create(
            {
                "service.name": service_name,
                "service.version": service_version,
                "deployment.environment": environment,
                "telemetry.sdk.name": "opentelemetry",
                "telemetry.sdk.language": "python",
            }
        )

        # Sampler (production: 1%, dev: 100%)
        sampler = TraceIdRatioBased(OTEL_SAMPLING_RATE)

        # TracerProvider
        _tracer_provider = TracerProvider(
            resource=resource,
            sampler=sampler,
        )

        # OTLP gRPC Exporter (Jaeger Collector)
        exporter = OTLPSpanExporter(
            endpoint=OTEL_EXPORTER_ENDPOINT,
            insecure=True,  # mTLS disabled for Jaeger (no sidecar)
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

        logger.info(
            "OpenTelemetry tracing configured",
            extra={
                "service": service_name,
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
            excluded_urls="health,ready,metrics",  # Health check 제외
        )
        logger.info("FastAPI instrumentation enabled")

    except ImportError:
        logger.warning("FastAPIInstrumentor not available")
    except Exception as e:
        logger.error(f"Failed to instrument FastAPI: {e}")


def instrument_sqlalchemy(engine) -> None:
    """SQLAlchemy 자동 계측 (DB 쿼리 추적)"""
    if not OTEL_ENABLED:
        return

    try:
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

        SQLAlchemyInstrumentor().instrument(engine=engine)
        logger.info("SQLAlchemy instrumentation enabled")

    except ImportError:
        logger.warning("SQLAlchemyInstrumentor not available")
    except Exception as e:
        logger.error(f"Failed to instrument SQLAlchemy: {e}")


def instrument_redis(redis_client) -> None:
    """Redis 자동 계측"""
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


def instrument_httpx() -> None:
    """HTTPX 자동 계측 (외부 API 호출 추적)"""
    if not OTEL_ENABLED:
        return

    try:
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

        HTTPXClientInstrumentor().instrument()
        logger.info("HTTPX instrumentation enabled")

    except ImportError:
        logger.warning("HTTPXClientInstrumentor not available")
    except Exception as e:
        logger.error(f"Failed to instrument HTTPX: {e}")


def shutdown_tracing() -> None:
    """트레이싱 종료 (graceful shutdown)"""
    global _tracer_provider

    if _tracer_provider is not None:
        try:
            _tracer_provider.shutdown()
            logger.info("OpenTelemetry tracing shutdown complete")
        except Exception as e:
            logger.error(f"Error shutting down tracing: {e}")


def get_tracer(name: str):
    """
    Tracer 인스턴스 반환 (수동 span 생성용)

    Usage:
        tracer = get_tracer(__name__)
        with tracer.start_as_current_span("operation") as span:
            span.set_attribute("key", "value")
            # ... business logic ...
    """
    if not OTEL_ENABLED:
        return None

    try:
        from opentelemetry import trace

        return trace.get_tracer(name)
    except ImportError:
        return None


def create_span(name: str, attributes: Optional[dict] = None):
    """
    수동 span 생성 컨텍스트 매니저

    Usage:
        with create_span("process_payment", {"amount": 100}) as span:
            # ... business logic ...
            span.add_event("payment_processed")
    """
    tracer = get_tracer(__name__)
    if tracer is None:
        from contextlib import nullcontext

        return nullcontext()

    span = tracer.start_as_current_span(name)
    if attributes:
        for key, value in attributes.items():
            span.set_attribute(key, value)
    return span
