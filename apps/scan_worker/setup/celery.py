"""Celery App Configuration.

⚠️ domains 의존성 제거 - apps 내부에서 라우팅 정의
"""

import logging
import os
from typing import Any

from celery import Celery
from celery.signals import worker_ready, worker_shutdown

from scan_worker.setup.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# Scan Worker Task Routes (태스크 = 큐 1:1)
SCAN_TASK_ROUTES = {
    "scan.vision": {"queue": "scan.vision"},
    "scan.rule": {"queue": "scan.rule"},
    "scan.answer": {"queue": "scan.answer"},
    "scan.reward": {"queue": "scan.reward"},
}

# Celery 앱 생성
celery_app = Celery(
    "scan_worker",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

# Task 모듈 자동 검색 (독립 모듈)
celery_app.autodiscover_tasks(
    [
        "scan_worker.presentation.tasks",
    ]
)

# Task 라우팅
celery_app.conf.task_routes = SCAN_TASK_ROUTES

# Celery 설정
celery_app.conf.update(
    task_track_started=True,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Seoul",
    enable_utc=True,
    worker_send_task_events=True,
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=100,
)


# ============================================================
# OpenTelemetry 분산 추적 (Celery Instrumentation)
# ============================================================


def _setup_celery_tracing() -> None:
    """Celery 태스크 분산 추적 설정 (Celery + Redis instrumentation)."""
    otel_enabled = os.getenv("OTEL_ENABLED", "true").lower() == "true"
    if not otel_enabled:
        logger.info("Celery tracing disabled (OTEL_ENABLED=false)")
        return

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter,
        )
        from opentelemetry.instrumentation.celery import CeleryInstrumentor
        from opentelemetry.instrumentation.redis import RedisInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        # TracerProvider 설정
        resource = Resource.create(
            {
                "service.name": "scan-worker",
                "service.version": os.getenv("SERVICE_VERSION", "1.0.0"),
                "deployment.environment": os.getenv("ENVIRONMENT", "dev"),
                "messaging.system": "redis",
                "messaging.destination.kind": "stream",
            }
        )

        provider = TracerProvider(resource=resource)
        endpoint = os.getenv(
            "OTEL_EXPORTER_OTLP_ENDPOINT",
            "http://jaeger-collector-clusterip.istio-system.svc.cluster.local:4318",
        )
        exporter = OTLPSpanExporter(endpoint=f"{endpoint}/v1/traces")
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)

        # Celery Instrumentation
        CeleryInstrumentor().instrument()
        logger.info("Celery tracing enabled", extra={"endpoint": endpoint})

        # Redis Instrumentation
        RedisInstrumentor().instrument()
        logger.info("Redis tracing enabled")

        # OpenAI Instrumentation
        try:
            from opentelemetry.instrumentation.openai_v2 import OpenAIInstrumentor

            OpenAIInstrumentor().instrument()
            logger.info("OpenAI tracing enabled")
        except ImportError:
            logger.warning("OpenAI instrumentor not available")

    except ImportError as e:
        logger.warning(f"Celery/Redis tracing not available: {e}")
    except Exception as e:
        logger.error(f"Failed to setup Celery tracing: {e}")


# ============================================================
# Worker 시작 시 리소스 초기화
# ============================================================


@worker_ready.connect
def init_worker_resources(sender: Any, **kwargs: Any) -> None:
    """Worker 시작 시 리소스 초기화.

    ⚠️ domains 의존성 제거됨:
    - domains._shared.cache (cache consumer)
    - domains._shared.celery.async_support (event loop)

    필요 시 apps/scan_worker/infrastructure/로 이동 예정
    """
    # 1. OpenTelemetry Celery 트레이싱 설정
    _setup_celery_tracing()

    logger.info("scan_worker_initialized")


@worker_shutdown.connect
def shutdown_worker_resources(sender: Any, **kwargs: Any) -> None:
    """Worker 종료 시 리소스 정리.

    ⚠️ domains 의존성 제거됨
    """
    logger.info("scan_worker_shutdown")
