"""Celery application instance.

모든 도메인에서 공유하는 Celery 앱 인스턴스를 생성합니다.
"""

from __future__ import annotations

from celery import Celery

from domains._shared.taskqueue.config import get_celery_settings

settings = get_celery_settings()

# Celery 앱 인스턴스 생성
celery_app = Celery(
    "eco2_tasks",
    broker=settings.broker_url,
    backend=settings.result_backend,
)

# 설정 적용
celery_app.conf.update(
    task_serializer=settings.task_serializer,
    result_serializer=settings.result_serializer,
    accept_content=settings.accept_content,
    timezone=settings.timezone,
    enable_utc=settings.enable_utc,
    task_acks_late=settings.task_acks_late,
    task_reject_on_worker_lost=settings.task_reject_on_worker_lost,
    result_expires=settings.result_expires,
    worker_prefetch_multiplier=settings.worker_prefetch_multiplier,
    worker_concurrency=settings.worker_concurrency,
    task_default_queue=settings.task_default_queue,
    task_create_missing_queues=settings.task_create_missing_queues,
    task_default_retry_delay=settings.task_default_retry_delay,
)

# Task 라우팅 설정
celery_app.conf.task_routes = {
    # Scan 도메인 태스크
    "domains.scan.tasks.classification.*": {"queue": "scan.classification"},
    "domains.scan.tasks.reward.*": {"queue": "scan.reward"},
    # 기본 태스크
    "domains.*": {"queue": "default"},
}

# Task autodiscover (각 도메인의 tasks 모듈을 자동 탐색)
# 실제 사용 시 명시적으로 등록하거나 아래 패턴 사용
# celery_app.autodiscover_tasks(["domains.scan.tasks"])
