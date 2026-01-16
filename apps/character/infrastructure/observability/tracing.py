"""OpenTelemetry Tracing - Character Service.

domains 의존성 제거 - 내부 모듈.
"""

import logging
import os

logger = logging.getLogger(__name__)

OTEL_EXPORTER_ENDPOINT = os.getenv(
    "OTEL_EXPORTER_OTLP_ENDPOINT",
    "jaeger-collector.istio-system.svc.cluster.local:4317",
)
OTEL_SAMPLING_RATE = float(os.getenv("OTEL_SAMPLING_RATE", "1.0"))
OTEL_ENABLED = os.getenv("OTEL_ENABLED", "true").lower() == "true"


def setup_tracing(service_name: str) -> bool:
    """OpenTelemetry 트레이싱 설정.

    Args:
        service_name: 서비스 이름

    Returns:
        설정 성공 여부
    """
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

        resource = Resource.create(
            {
                "service.name": service_name,
                "service.version": os.getenv("SERVICE_VERSION", "1.0.0"),
                "deployment.environment": os.getenv("ENVIRONMENT", "dev"),
            }
        )

        sampler = TraceIdRatioBased(OTEL_SAMPLING_RATE)
        provider = TracerProvider(resource=resource, sampler=sampler)

        exporter = OTLPSpanExporter(
            endpoint=OTEL_EXPORTER_ENDPOINT,
            insecure=True,
        )

        provider.add_span_processor(
            BatchSpanProcessor(
                exporter,
                max_queue_size=2048,
                max_export_batch_size=512,
                schedule_delay_millis=1000,
            )
        )

        trace.set_tracer_provider(provider)

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


def instrument_fastapi(app) -> None:
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
    """HTTPX 자동 계측."""
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
    """Redis 자동 계측 (캐시 추적)."""
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
    # TracerProvider는 global이므로 shutdown은 필요하지 않음
    # 향후 _tracer_provider를 저장하여 shutdown 구현 가능
    pass
