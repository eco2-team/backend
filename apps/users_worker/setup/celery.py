"""Celery Application.

users-worker에서 사용하는 Celery 앱 인스턴스입니다.

⚠️ 큐 생성은 RabbitMQ Topology CR에 위임
   (workloads/rabbitmq/base/topology/queues.yaml)
   Python에서는 task routing만 정의
"""

from __future__ import annotations

import logging
import os
from typing import Any

from celery import Celery
from celery.signals import worker_ready

from users_worker.setup.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# Users Worker Task Routes (태스크 = 큐 1:1)
# ⚠️ 큐 이름은 Topology CR과 일치해야 함
# ⚠️ reward.character는 Named Exchange (reward.direct)로 발행됨
#    Binding: reward.character routing_key → users.save_character 큐
USERS_TASK_ROUTES = {
    "users.save_character": {"queue": "users.save_character"},
    "reward.character": {"queue": "users.save_character"},  # 1:N 이벤트
}

# Celery 앱 생성
celery_app = Celery("users_worker")

# 설정 적용
celery_app.conf.update(
    broker_url=settings.celery_broker_url,
    result_backend=settings.celery_result_backend,
    task_routes=USERS_TASK_ROUTES,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Seoul",
    enable_utc=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
)

# Task 모듈 자동 검색
celery_app.autodiscover_tasks(
    [
        "users_worker.presentation.tasks",
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
                "service.name": "users-worker",
                "service.version": os.getenv("SERVICE_VERSION", "1.0.0"),
                "deployment.environment": settings.environment,
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
            extra={"endpoint": endpoint, "service": "users-worker"},
        )

    except ImportError as e:
        logger.warning(f"Celery tracing not available: {e}")
    except Exception as e:
        logger.error(f"Failed to setup Celery tracing: {e}")


@worker_ready.connect
def on_worker_ready(sender: Any, **kwargs: Any) -> None:
    """Worker 시작 시 리소스 초기화."""
    # 1. OpenTelemetry Celery 트레이싱 설정
    _setup_celery_tracing()

    logger.info("users_worker_started", extra={"hostname": sender.hostname})
