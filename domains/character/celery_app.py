"""
Character Domain Celery Application

character-worker에서 사용하는 Celery 앱 인스턴스
- reward.character 큐: 캐릭터 보상 판정
- reward.persist 큐: 캐릭터 소유권 저장
"""

import logging
import os
from typing import Any

from celery import Celery
from celery.signals import worker_ready, worker_shutdown

from domains._shared.celery.config import get_celery_settings

logger = logging.getLogger(__name__)
settings = get_celery_settings()

# Celery 앱 생성
celery_app = Celery("character")

# 설정 적용
celery_app.conf.update(settings.get_celery_config())

# Task 모듈 자동 검색
celery_app.autodiscover_tasks(
    [
        "domains.character.tasks",
        "domains._shared.celery",  # DLQ 재처리 Task
    ]
)


# ============================================================
# OpenTelemetry 분산 추적 (Celery Instrumentation)
# ============================================================


def _setup_celery_tracing() -> None:
    """Celery 태스크 분산 추적 설정."""
    otel_enabled = os.getenv("OTEL_ENABLED", "true").lower() == "true"
    if not otel_enabled:
        logger.info("Celery tracing disabled (OTEL_ENABLED=false)")
        return

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
            OTLPSpanExporter,
        )
        from opentelemetry.instrumentation.celery import CeleryInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        # TracerProvider 설정
        resource = Resource.create(
            {
                "service.name": "character-worker",
                "service.version": os.getenv("SERVICE_VERSION", "1.0.0"),
                "deployment.environment": os.getenv("ENVIRONMENT", "dev"),
            }
        )

        provider = TracerProvider(resource=resource)
        endpoint = os.getenv(
            "OTEL_EXPORTER_OTLP_ENDPOINT",
            "jaeger-collector.istio-system.svc.cluster.local:4317",
        )
        exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)

        # Celery Instrumentation
        CeleryInstrumentor().instrument()
        logger.info(
            "Celery tracing enabled",
            extra={"endpoint": endpoint, "service": "character-worker"},
        )

    except ImportError as e:
        logger.warning(f"Celery tracing not available: {e}")
    except Exception as e:
        logger.error(f"Failed to setup Celery tracing: {e}")


# ============================================================
# Worker 시작 시 리소스 초기화
# ============================================================


@worker_ready.connect
def init_character_cache(sender: Any, **kwargs: Any) -> None:
    """Worker 시작 시 리소스 초기화.

    1. OpenTelemetry Celery 트레이싱 설정
    2. 캐시 Consumer 시작
    """
    from domains._shared.cache import start_cache_consumer

    # 1. OpenTelemetry Celery 트레이싱 설정 (worker_ready 시점에 호출)
    _setup_celery_tracing()

    # 2. 캐시 Consumer 시작
    logger.info("character_worker_cache_consumer_starting")

    try:
        broker_url = os.getenv("CELERY_BROKER_URL")
        if broker_url:
            start_cache_consumer(broker_url)
            logger.info("character_worker_cache_consumer_started")
        else:
            logger.warning("character_worker_cache_consumer_skipped_no_broker")
    except Exception:
        logger.exception("character_worker_cache_consumer_failed")


@worker_shutdown.connect
def shutdown_character_cache_consumer(sender: Any, **kwargs: Any) -> None:
    """Worker 종료 시 캐시 Consumer 정리."""
    from domains._shared.cache import stop_cache_consumer

    try:
        stop_cache_consumer()
        logger.info("character_worker_cache_consumer_stopped")
    except Exception:
        logger.exception("character_worker_cache_shutdown_failed")
