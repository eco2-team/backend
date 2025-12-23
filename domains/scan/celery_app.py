"""
Scan Domain Celery Application

scan-worker에서 사용하는 Celery 앱 인스턴스
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
celery_app = Celery("scan")

# 설정 적용
celery_app.config_from_object(settings.get_celery_config())

# Task 모듈 자동 검색
celery_app.autodiscover_tasks(
    [
        "domains.scan.tasks",
        "domains._shared.celery",  # DLQ 재처리 Task
    ]
)


# ============================================================
# Worker 시작 시 캐릭터 캐시 초기화 (scan-worker용)
# Note: scan.reward는 character-worker에서 실행되지만,
#       일관성을 위해 scan-worker에서도 캐시 Consumer를 시작
# ============================================================


@worker_ready.connect
def init_character_cache_for_scan(sender: Any, **kwargs: Any) -> None:
    """Worker 시작 시 캐시 Consumer 시작."""
    from domains._shared.cache import start_cache_consumer

    logger.info("scan_worker_cache_consumer_starting")

    try:
        broker_url = os.getenv("CELERY_BROKER_URL")
        if broker_url:
            start_cache_consumer(broker_url)
            logger.info("scan_worker_cache_consumer_started")
        else:
            logger.warning("scan_worker_cache_consumer_skipped_no_broker")
    except Exception:
        logger.exception("scan_worker_cache_consumer_failed")


@worker_shutdown.connect
def shutdown_character_cache_for_scan(sender: Any, **kwargs: Any) -> None:
    """Worker 종료 시 캐시 Consumer 정리."""
    from domains._shared.cache import stop_cache_consumer

    try:
        stop_cache_consumer()
        logger.info("scan_worker_cache_consumer_stopped")
    except Exception:
        logger.exception("scan_worker_cache_shutdown_failed")
