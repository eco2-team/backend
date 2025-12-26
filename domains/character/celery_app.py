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


def _load_initial_cache() -> None:
    """DB에서 캐릭터 목록을 로드하여 캐시 초기화.

    HPA 스케일아웃 시 새 Pod가 빈 캐시로 시작하는 문제 해결.
    fanout 이벤트를 기다리지 않고 직접 DB에서 로드.
    """
    import asyncio

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    from domains._shared.cache import get_character_cache

    db_url = os.getenv("CHARACTER_DATABASE_URL")
    if not db_url:
        logger.warning("character_cache_load_skipped_no_db_url")
        return

    cache = get_character_cache()
    if cache.is_initialized:
        logger.info(
            "character_cache_already_initialized",
            extra={"count": cache.count()},
        )
        return

    async def _load() -> list[dict]:
        engine = create_async_engine(db_url, echo=False, pool_pre_ping=True)
        try:
            async with engine.connect() as conn:
                result = await conn.execute(
                    text(
                        "SELECT id, code, name, match_label, type_label, dialog "
                        "FROM character.characters"
                    )
                )
                return [
                    {
                        "id": str(row[0]),
                        "code": row[1],
                        "name": row[2],
                        "match_label": row[3],
                        "type_label": row[4],
                        "dialog": row[5],
                    }
                    for row in result.fetchall()
                ]
        finally:
            await engine.dispose()

    try:
        characters = asyncio.run(_load())
        cache.set_all(characters)
        logger.info(
            "character_cache_loaded_from_db",
            extra={"count": len(characters)},
        )
    except Exception:
        logger.exception("character_cache_load_from_db_failed")


@worker_ready.connect
def init_character_cache(sender: Any, **kwargs: Any) -> None:
    """Worker 시작 시 리소스 초기화.

    1. OpenTelemetry Celery 트레이싱 설정
    2. 캐시 Consumer 시작 (fanout 이벤트 수신용)
    3. DB에서 초기 캐시 로드 (HPA 스케일아웃 대응)
    """
    from domains._shared.cache import start_cache_consumer

    # 1. OpenTelemetry Celery 트레이싱 설정 (worker_ready 시점에 호출)
    _setup_celery_tracing()

    # 2. 캐시 Consumer 시작 (실시간 동기화용)
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

    # 3. DB에서 초기 캐시 로드 (HPA 스케일아웃 시 빈 캐시 방지)
    _load_initial_cache()


@worker_shutdown.connect
def shutdown_character_cache_consumer(sender: Any, **kwargs: Any) -> None:
    """Worker 종료 시 캐시 Consumer 정리."""
    from domains._shared.cache import stop_cache_consumer

    try:
        stop_cache_consumer()
        logger.info("character_worker_cache_consumer_stopped")
    except Exception:
        logger.exception("character_worker_cache_shutdown_failed")
