"""Celery Application.

users-worker에서 사용하는 Celery 앱 인스턴스입니다.

⚠️ 큐 생성은 RabbitMQ Topology CR에 위임
   (workloads/rabbitmq/base/topology/queues.yaml)
   Python에서는 task routing만 정의
⚠️ task_queues는 이름만 정의 (arguments 없음 → 기존 큐 그대로 사용)
"""

from __future__ import annotations

import logging
import os
from typing import Any

from celery import Celery
from celery.signals import worker_ready
from kombu import Queue

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

# 소비할 큐 정의 (이름만, arguments 없음 → Topology CR 정의 사용)
# task_create_missing_queues=False 시 -Q 옵션 사용을 위해 필요
# no_declare=True: Celery가 큐를 선언하지 않음 (Topology CR이 생성)
# ⚠️ exchange="", routing_key=<queue_name> 명시 → AMQP Default Exchange 사용
USERS_TASK_QUEUES = [
    Queue("users.save_character", exchange="", routing_key="users.save_character", no_declare=True),
]

# Celery 앱 생성
celery_app = Celery("users_worker")

# 설정 적용
celery_app.conf.update(
    broker_url=settings.celery_broker_url,
    result_backend=settings.celery_result_backend,
    task_routes=USERS_TASK_ROUTES,
    task_queues=USERS_TASK_QUEUES,  # -Q 옵션 사용을 위해 필요
    # 큐 생성을 Topology CR에 위임 (TTL, DLX 등 인자 충돌 방지)
    task_create_missing_queues=False,
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
            extra={"endpoint": endpoint, "service_name": "users-worker"},
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
