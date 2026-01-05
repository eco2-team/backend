"""Scan Celery Application."""

from __future__ import annotations

import os

from celery import Celery

# Celery 앱 생성 (기존 domains/scan과 동일한 설정)
celery_app = Celery("scan")

# 브로커 URL
broker_url = os.getenv(
    "CELERY_BROKER_URL",
    "amqp://admin:admin@localhost:5672/eco2",
)

celery_app.conf.update(
    broker_url=broker_url,
    # 결과 백엔드 비활성화 (Redis Streams 사용)
    result_backend=None,
    # Task 설정
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Seoul",
    enable_utc=True,
    # Worker 설정
    worker_prefetch_multiplier=1,  # gevent 사용 시 1로 설정
    worker_concurrency=10,
    # Task 라우팅 (큐별 분리)
    task_routes={
        "scan.vision": {"queue": "scan.vision"},
        "scan.rule": {"queue": "scan.rule"},
        "scan.answer": {"queue": "scan.answer"},
        "scan.reward": {"queue": "scan.reward"},
    },
    # Task 기본 설정
    task_default_queue="scan.default",
    task_default_exchange="scan",
    task_default_routing_key="scan.default",
    # 이벤트 설정 (레거시 호환)
    task_send_sent_event=True,
    worker_send_task_events=True,
    # Acks Late (안전한 재시도)
    task_acks_late=True,
    task_reject_on_worker_lost=True,
)

# Task 자동 검색 (workers 모듈)
celery_app.autodiscover_tasks(["apps.scan.workers"])
