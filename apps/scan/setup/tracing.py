"""OpenTelemetry Distributed Tracing Configuration for Scan API.

분산 트레이싱 설정:
- FastAPI 자동 계측 (HTTP 요청/응답)
- HTTPX 자동 계측 (외부 API 호출)
- Redis 자동 계측 (Streams, Pub/Sub)

Architecture:
  Scan API (OTel SDK) -> OTLP/HTTP (4318) -> Jaeger Collector
"""

import logging
import os

from fastapi import FastAPI

logger = logging.getLogger(__name__)

# Environment variables
OTEL_EXPORTER_ENDPOINT = os.getenv(
    "OTEL_EXPORTER_OTLP_ENDPOINT",
    "http://jaeger-collector-clusterip.istio-system.svc.cluster.local:4318",
)
OTEL_SAMPLING_RATE = float(os.getenv("OTEL_SAMPLING_RATE", "1.0"))
OTEL_ENABLED = os.getenv("OTEL_ENABLED", "true").lower() == "true"

# Service constants
SERVICE_NAME = "scan-api"
SERVICE_VERSION = os.getenv("SERVICE_VERSION", "1.0.0")
ENVIRONMENT = os.getenv("ENVIRONMENT", "dev")

# Lazy initialization
_tracer_provider = None


def configure_tracing() -> bool:
    """OpenTelemetry 트레이싱 설정.

    Returns:
        bool: 설정 성공 여부
    """
    global _tracer_provider

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

        # Resource attributes
        resource = Resource.create(
            {
                "service.name": SERVICE_NAME,
                "service.version": SERVICE_VERSION,
                "deployment.environment": ENVIRONMENT,
                "telemetry.sdk.name": "opentelemetry",
                "telemetry.sdk.language": "python",
            }
        )

        # Sampler
        sampler = TraceIdRatioBased(OTEL_SAMPLING_RATE)

        # TracerProvider
        _tracer_provider = TracerProvider(
            resource=resource,
            sampler=sampler,
        )

        # OTLP HTTP Exporter
        exporter = OTLPSpanExporter(
            endpoint=f"{OTEL_EXPORTER_ENDPOINT}/v1/traces",
        )

        # BatchSpanProcessor
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
    """FastAPI 자동 계측."""
    if not OTEL_ENABLED:
        return

    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor.instrument_app(
            app,
            excluded_urls="health,ready,metrics",
        )
        logger.info("FastAPI instrumentation enabled")

    except ImportError:
        logger.warning("FastAPIInstrumentor not available")
    except Exception as e:
        logger.error(f"Failed to instrument FastAPI: {e}")


def instrument_httpx() -> None:
    """HTTPX 자동 계측 (Vision API 호출 추적)."""
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


def instrument_redis() -> None:
    """Redis 자동 계측 (Streams 발행 추적)."""
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
    """트레이싱 종료."""
    global _tracer_provider

    if _tracer_provider is not None:
        try:
            _tracer_provider.shutdown()
            logger.info("OpenTelemetry tracing shutdown complete")
        except Exception as e:
            logger.error(f"Error shutting down tracing: {e}")


def get_tracer(name: str = SERVICE_NAME):
    """Tracer 인스턴스 반환."""
    if not OTEL_ENABLED:
        return None

    try:
        from opentelemetry import trace

        return trace.get_tracer(name)
    except ImportError:
        return None
