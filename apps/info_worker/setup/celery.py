"""Celery Configuration for Info Worker."""

from celery import Celery

from info_worker.setup.config import get_settings

settings = get_settings()

# Celery App
celery_app = Celery("info_worker")

# Task Routing
INFO_TASK_ROUTES = {
    "info.collect_news": {"queue": "info.collect_news"},
    "info.collect_news_newsdata": {"queue": "info.collect_news"},
}

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
    task_default_queue="info.collect_news",
    task_create_missing_queues=False,  # RabbitMQ Topology CR에서 생성
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
