"""
Scan Domain Celery Application

scan-worker에서 사용하는 Celery 앱 인스턴스
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
celery_app = Celery("scan")

# 설정 적용 (dict는 conf.update 사용)
celery_app.conf.update(settings.get_celery_config())

# Task 모듈 자동 검색
celery_app.autodiscover_tasks(
    [
        "domains.scan.tasks",
        "domains._shared.celery",  # DLQ 재처리 Task
    ]
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
                # Worker 특화 속성
                "messaging.system": "redis",
                "messaging.destination.kind": "stream",
            }
        )

        provider = TracerProvider(resource=resource)
        endpoint = os.getenv(
            "OTEL_EXPORTER_OTLP_ENDPOINT",
            "http://jaeger-collector-clusterip.istio-system.svc.cluster.local:4318",
        )
        # HTTP/protobuf exporter (Istio 호환성 향상)
        exporter = OTLPSpanExporter(endpoint=f"{endpoint}/v1/traces")
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)

        # Celery Instrumentation
        CeleryInstrumentor().instrument()
        logger.info("Celery tracing enabled", extra={"endpoint": endpoint})

        # Redis Instrumentation (Streams XADD, Cache 등 추적)
        RedisInstrumentor().instrument()
        logger.info("Redis tracing enabled (Streams/Cache)")

        # OpenAI Instrumentation (Vision, Answer API 호출 추적)
        try:
            from opentelemetry.instrumentation.openai_v2 import OpenAIInstrumentor

            OpenAIInstrumentor().instrument()
            logger.info("OpenAI tracing enabled (Vision/Answer)")
        except ImportError:
            logger.warning("OpenAI instrumentor not available")

    except ImportError as e:
        logger.warning(f"Celery/Redis tracing not available: {e}")
    except Exception as e:
        logger.error(f"Failed to setup Celery tracing: {e}")


# ============================================================
# Worker 시작 시 리소스 초기화 (scan-worker용)
# ============================================================


@worker_ready.connect
def init_worker_resources(sender: Any, **kwargs: Any) -> None:
    """Worker 시작 시 리소스 초기화.

    1. OpenTelemetry Celery 트레이싱 설정
    2. 공유 event loop 초기화 (prefork pool에서만 필요)
    3. 캐시 Consumer 시작
    """
    from domains._shared.cache import start_cache_consumer

    # 1. OpenTelemetry Celery 트레이싱 설정 (worker_ready 시점에 호출해야 로그 출력됨)
    _setup_celery_tracing()

    # 2. Event loop 초기화 (prefork pool에서만 필요)
    # gevent pool: 자동 greenlet 전환으로 불필요
    pool_cls = os.getenv("CELERY_WORKER_POOL", "prefork")
    if pool_cls == "prefork":
        try:
            from domains._shared.celery.async_support import init_event_loop

            init_event_loop()
            logger.info("scan_worker_event_loop_initialized (prefork pool)")
        except Exception:
            logger.exception("scan_worker_event_loop_init_failed")
    else:
        logger.info(f"scan_worker_using_{pool_cls}_pool (auto greenlet/coroutine switch)")

    # 3. 캐시 Consumer 시작
    logger.info("scan_worker_cache_consumer_starting")
    try:
        broker_url = os.getenv("CELERY_BROKER_URL")
        if broker_url:
            start_cache_consumer(broker_url)
            logger.info("scan_worker_cache_consumer_started")
        else:
            logger.warning("scan_worker_cache_consumer_skipped_no_broker")
    except Exception:
        logger.exception("scan_worker_cache_consumer_failed")


@worker_shutdown.connect
def shutdown_worker_resources(sender: Any, **kwargs: Any) -> None:
    """Worker 종료 시 리소스 정리."""
    from domains._shared.cache import stop_cache_consumer

    # 1. 캐시 Consumer 정리
    try:
        stop_cache_consumer()
        logger.info("scan_worker_cache_consumer_stopped")
    except Exception:
        logger.exception("scan_worker_cache_shutdown_failed")

    # 2. Event loop 정리 (prefork pool에서만 필요)
    pool_cls = os.getenv("CELERY_WORKER_POOL", "prefork")
    if pool_cls == "prefork":
        try:
            from domains._shared.celery.async_support import shutdown_event_loop

            shutdown_event_loop()
            logger.info("scan_worker_event_loop_shutdown")
        except Exception:
            logger.exception("scan_worker_event_loop_shutdown_failed")
