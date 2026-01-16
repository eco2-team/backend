"""Celery Configuration for Info Worker.

⚠️ 큐 생성은 RabbitMQ Topology CR에 위임
   (workloads/rabbitmq/base/topology/queues.yaml)
   Python에서는 task routing만 정의
⚠️ task_queues는 이름만 정의 (arguments 없음 → 기존 큐 그대로 사용)
"""

from celery import Celery
from kombu import Queue

from info_worker.setup.config import get_settings

settings = get_settings()

# Info Worker Task Routes (태스크 = 큐 1:1)
# ⚠️ 큐 이름은 Topology CR과 일치해야 함
INFO_TASK_ROUTES = {
    "info.collect_news": {"queue": "info.collect_news"},
    "info.collect_news_newsdata": {"queue": "info.collect_news"},
}

# 소비할 큐 정의 (이름만, arguments 없음 → Topology CR 정의 사용)
# task_create_missing_queues=False 시 -Q 옵션 사용을 위해 필요
# no_declare=True: Celery가 큐를 선언하지 않음 (Topology CR이 생성)
# ⚠️ exchange="", routing_key=<queue_name> 명시 → AMQP Default Exchange 사용
INFO_TASK_QUEUES = [
    Queue("info.collect_news", exchange="", routing_key="info.collect_news", no_declare=True),
]

# Celery App
celery_app = Celery("info_worker")

# Configuration
celery_app.conf.update(
    # Broker & Backend
    broker_url=settings.celery_broker_url,
    result_backend=settings.celery_result_backend,
    # Serialization
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    # Timezone
    timezone="Asia/Seoul",
    enable_utc=True,
    # Task Routing
    task_routes=INFO_TASK_ROUTES,
    task_queues=INFO_TASK_QUEUES,  # -Q 옵션 사용을 위해 필요
    task_default_queue="info.collect_news",
    task_default_exchange="",  # AMQP default exchange (direct routing)
    task_default_routing_key="info.collect_news",
    # 큐 생성을 Topology CR에 위임 (TTL, DLX 등 인자 충돌 방지)
    task_create_missing_queues=False,
    # Worker
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    # Beat Schedule (주기적 뉴스 수집)
    beat_schedule={
        # Naver 뉴스 수집 (5분 주기)
        "collect-news-naver": {
            "task": "info.collect_news",
            "schedule": float(settings.collect_interval_naver),
            "kwargs": {"category": "all", "source": "naver"},
        },
        # NewsData.io 수집 (30분 주기 - Rate Limit 대응)
        "collect-news-newsdata": {
            "task": "info.collect_news_newsdata",
            "schedule": float(settings.collect_interval_newsdata),
            "kwargs": {"category": "all"},
        },
    },
)

# Task imports
celery_app.autodiscover_tasks(["info_worker.presentation.tasks"])
