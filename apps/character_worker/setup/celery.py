"""Celery Application Setup.

⚠️ domains 의존성 제거 - apps 내부에서 라우팅 정의
⚠️ 큐 생성은 Topology CR에 위임 (task_create_missing_queues=False)
   task_queues는 이름만 정의 (arguments 없음 → 기존 큐 그대로 사용)

분산 트레이싱 통합:
- Celery Instrumentation으로 Task 실행 추적
- Jaeger/Kiali에서 API → MQ → Worker 흐름 추적 가능
"""

import logging
import os

from celery import Celery
from celery.signals import worker_process_init, worker_ready
from kombu import Queue

from character_worker.setup.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# Character Worker Task Routes (태스크 = 큐 1:1)
# ⚠️ reward.character는 Named Exchange (reward.direct)로 발행됨
#    Binding: reward.character routing_key → character.save_ownership 큐
CHARACTER_TASK_ROUTES = {
    "character.match": {"queue": "character.match"},
    "character.save_ownership": {"queue": "character.save_ownership"},
    "character.grant_default": {"queue": "character.grant_default"},
    "reward.character": {"queue": "character.save_ownership"},  # 1:N 이벤트
}

# 소비할 큐 정의 (이름만, arguments 없음 → Topology CR 정의 사용)
# task_create_missing_queues=False 시 -Q 옵션 사용을 위해 필요
# no_declare=True: Celery가 큐를 선언하지 않음 (Topology CR이 생성)
# ⚠️ exchange="", routing_key=<queue_name> 명시 → AMQP Default Exchange 사용
CHARACTER_TASK_QUEUES = [
    Queue("character.match", exchange="", routing_key="character.match", no_declare=True),
    Queue(
        "character.save_ownership",
        exchange="",
        routing_key="character.save_ownership",
        no_declare=True,
    ),
    Queue(
        "character.grant_default",
        exchange="",
        routing_key="character.grant_default",
        no_declare=True,
    ),
]

# Celery 앱 생성
celery_app = Celery(
    "character_worker",
    broker=settings.broker_url,
    include=[
        "character_worker.presentation.tasks.match_task",
        "character_worker.presentation.tasks.ownership_task",
        "character_worker.presentation.tasks.grant_default_task",
        "character_worker.presentation.tasks.reward_event_task",
    ],
)

# Celery 설정
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Seoul",
    enable_utc=True,
    task_routes=CHARACTER_TASK_ROUTES,
    task_queues=CHARACTER_TASK_QUEUES,  # -Q 옵션 사용을 위해 필요
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    # 큐 생성을 Topology CR에 위임 (TTL, DLX 등 인자 충돌 방지)
    task_create_missing_queues=False,
)


def _init_character_cache() -> bool:
    """캐릭터 캐시를 DB에서 로드하는 공통 로직.

    Returns:
        True: 캐시 로드 성공 또는 이미 로드됨
        False: 캐시 로드 실패
    """
    from sqlalchemy import text

    from character_worker.domain import Character
    from character_worker.infrastructure.cache import get_character_cache
    from character_worker.setup.database import sync_session_factory

    cache = get_character_cache()

    if cache.is_loaded():
        logger.info("Character cache already loaded")
        return True

    # DB에서 캐릭터 로드
    try:
        with sync_session_factory() as session:
            result = session.execute(
                text(
                    """
                    SELECT id, code, name, type_label, dialog, match_label
                    FROM character.characters
                    WHERE match_label IS NOT NULL
                """
                )
            )
            rows = result.fetchall()

            characters: dict[str, Character] = {}
            for row in rows:
                char = Character(
                    id=row.id,
                    code=row.code,
                    name=row.name,
                    type_label=row.type_label,
                    dialog=row.dialog,
                    match_label=row.match_label,
                )
                if row.match_label:
                    characters[row.match_label] = char

            cache.load(characters, settings.default_character_code)
            logger.info(
                "Character cache initialized from DB",
                extra={"count": len(characters)},
            )
            return True

    except Exception as e:
        logger.warning(f"Failed to initialize character cache: {e}")
        return False


@worker_process_init.connect
def init_worker_process(**kwargs):
    """Worker 프로세스 초기화 (prefork pool 전용).

    prefork pool에서 각 worker process가 fork될 때 호출됩니다.
    gevent/threads pool에서는 호출되지 않음.
    """
    logger.info("Initializing character worker process (worker_process_init)")
    _init_character_cache()


def _setup_celery_tracing() -> None:
    """Celery 태스크 분산 추적 설정."""
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
            "http://jaeger-collector-clusterip.istio-system.svc.cluster.local:4318",
        )
        exporter = OTLPSpanExporter(endpoint=f"{endpoint}/v1/traces")
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)

        # Celery Instrumentation
        CeleryInstrumentor().instrument()
        logger.info(
            "Celery tracing enabled",
            extra={"endpoint": endpoint, "service_name": "character-worker"},
        )

    except ImportError as e:
        logger.warning(f"Celery tracing not available: {e}")
    except Exception as e:
        logger.error(f"Failed to setup Celery tracing: {e}")


@worker_ready.connect
def init_worker_ready(**kwargs):
    """Worker 준비 완료 시 초기화 (모든 pool 타입).

    모든 pool 타입에서 worker가 준비되면 호출됩니다.
    캐시가 이미 로드되었으면 skip합니다.
    실패해도 task 실행 시 lazy loading으로 재시도합니다.
    """
    logger.info("Initializing character worker (worker_ready)")

    # 1. OpenTelemetry Celery 트레이싱 설정
    _setup_celery_tracing()

    # 2. 캐릭터 캐시 초기화
    if not _init_character_cache():
        logger.info("Cache will be loaded on first task execution (lazy loading)")
