"""Scan Celery Application.

scan-worker와 동일한 큐 설정 사용 (TTL + DLX).
⚠️ 큐 arguments가 다르면 PRECONDITION_FAILED 발생.
"""

from __future__ import annotations

import os

from celery import Celery
from kombu import Exchange, Queue

# Celery 앱 생성
celery_app = Celery("scan")

# 브로커 URL
broker_url = os.getenv(
    "CELERY_BROKER_URL",
    "amqp://admin:admin@localhost:5672/eco2",
)

# RabbitMQ Exchange 설정 (AMQP default exchange - domains와 동일)
DEFAULT_EXCHANGE = Exchange("", type="direct")

# Dead Letter Exchange
DLX_EXCHANGE = "dlx"

# 큐별 TTL 설정 (scan_worker와 동일)
QUEUE_TTL_MAP = {
    "scan.vision": 3600000,  # 1시간
    "scan.rule": 300000,  # 5분
    "scan.answer": 3600000,  # 1시간
    "scan.reward": 3600000,  # 1시간
}


def _queue_args(queue_name: str) -> dict:
    """큐별 arguments 생성 (TTL + DLX + DLQ 라우팅키)."""
    return {
        "x-message-ttl": QUEUE_TTL_MAP.get(queue_name, 3600000),
        "x-dead-letter-exchange": DLX_EXCHANGE,
        "x-dead-letter-routing-key": f"dlq.{queue_name}",
    }


# 기본 큐 (task_create_missing_queues=False 때문에 필요)
CELERY_DEFAULT_QUEUE = Queue(
    "celery",
    exchange=DEFAULT_EXCHANGE,
    routing_key="celery",
    queue_arguments={
        "x-message-ttl": 3600000,
        "x-dead-letter-exchange": DLX_EXCHANGE,
        "x-dead-letter-routing-key": "dlq.celery",
    },
)

# 큐 설정 (scan_worker와 동일 - AMQP default exchange)
SCAN_TASK_QUEUES = (
    CELERY_DEFAULT_QUEUE,
    Queue(
        "scan.vision",
        exchange=DEFAULT_EXCHANGE,
        routing_key="scan.vision",
        queue_arguments=_queue_args("scan.vision"),
    ),
    Queue(
        "scan.rule",
        exchange=DEFAULT_EXCHANGE,
        routing_key="scan.rule",
        queue_arguments=_queue_args("scan.rule"),
    ),
    Queue(
        "scan.answer",
        exchange=DEFAULT_EXCHANGE,
        routing_key="scan.answer",
        queue_arguments=_queue_args("scan.answer"),
    ),
    Queue(
        "scan.reward",
        exchange=DEFAULT_EXCHANGE,
        routing_key="scan.reward",
        queue_arguments=_queue_args("scan.reward"),
    ),
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
    # 큐 설정 (scan_worker와 동일한 arguments)
    task_queues=SCAN_TASK_QUEUES,
    # Task 라우팅 (큐별 분리)
    task_routes={
        "scan.vision": {"queue": "scan.vision"},
        "scan.rule": {"queue": "scan.rule"},
        "scan.answer": {"queue": "scan.answer"},
        "scan.reward": {"queue": "scan.reward"},
    },
    # Task 기본 설정 (AMQP default exchange - domains와 동일)
    task_default_queue="celery",
    task_default_exchange="",  # AMQP default exchange
    task_default_routing_key="celery",
    # 큐 자동 생성 비활성화 (RabbitMQ Topology CR로 생성된 큐 사용)
    task_create_missing_queues=False,
    # 이벤트 설정 (레거시 호환)
    task_send_sent_event=True,
    worker_send_task_events=True,
    # Acks Late (안전한 재시도)
    task_acks_late=True,
    task_reject_on_worker_lost=True,
)
