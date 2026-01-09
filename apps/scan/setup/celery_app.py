"""Scan API Celery Application.

scan-api는 Task 발행(produce)만 담당.
큐 생성/소비는 scan_worker와 RabbitMQ Topology CR이 담당.
"""

from __future__ import annotations

import os

from celery import Celery

# Celery 앱 생성
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
    # Task 직렬화 설정
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Seoul",
    enable_utc=True,
    # Task 라우팅 (발행 시 어느 큐로 보낼지 결정)
    task_routes={
        "scan.vision": {"queue": "scan.vision"},
        "scan.rule": {"queue": "scan.rule"},
        "scan.answer": {"queue": "scan.answer"},
        "scan.reward": {"queue": "scan.reward"},
    },
    # AMQP default exchange 사용 (큐 이름 = routing key)
    task_default_queue="celery",
    task_default_exchange="",  # AMQP default exchange
    task_default_routing_key="celery",
    # ⚠️ 핵심: 큐 생성을 시도하지 않음 (Topology CR에 위임)
    task_create_missing_queues=False,
    # task_queues 제거 → 발행자는 큐 정의 불필요
    # 이벤트 설정
    task_send_sent_event=True,
)
