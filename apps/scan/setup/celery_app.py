"""Scan API Celery Application.

scan-api는 Task 발행(produce)만 담당.
큐 생성은 RabbitMQ Topology CR이 담당 → no_declare=True.
"""

from __future__ import annotations

import os

from celery import Celery
from kombu import Queue

# Celery 앱 생성
celery_app = Celery("scan")

# 브로커 URL
broker_url = os.getenv(
    "CELERY_BROKER_URL",
    "amqp://admin:admin@localhost:5672/eco2",
)

# 큐 정의 (라우팅용, 큐 생성은 Topology CR에 위임)
# no_declare=True: Queue.declare() 호출 방지
SCAN_TASK_QUEUES = [
    Queue("celery", no_declare=True),
    Queue("scan.vision", no_declare=True),
    Queue("scan.rule", no_declare=True),
    Queue("scan.answer", no_declare=True),
    Queue("scan.reward", no_declare=True),
]

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
    # 큐 정의 (라우팅에 필요, no_declare=True로 선언 방지)
    task_queues=SCAN_TASK_QUEUES,
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
    # 큐 생성을 시도하지 않음 (Topology CR에 위임)
    task_create_missing_queues=False,
    # 이벤트 설정
    task_send_sent_event=True,
)
