"""
My Domain Celery Application

my-worker에서 사용하는 Celery 앱 인스턴스
- my.sync 큐: 유저 캐릭터 DB 동기화
"""

import logging
from typing import Any

from celery import Celery
from celery.signals import worker_ready

from domains._shared.celery.config import get_celery_settings

logger = logging.getLogger(__name__)
settings = get_celery_settings()

# Celery 앱 생성
celery_app = Celery("my")

# 설정 적용
celery_app.config_from_object(settings.get_celery_config())

# Task 모듈 자동 검색
celery_app.autodiscover_tasks(
    [
        "domains.my.tasks",
        "domains._shared.celery",  # DLQ 재처리 Task
    ]
)


@worker_ready.connect
def on_worker_ready(sender: Any, **kwargs: Any) -> None:
    """Worker 시작 시 로깅."""
    logger.info("my_worker_started", extra={"hostname": sender.hostname})
