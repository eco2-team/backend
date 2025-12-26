"""
Scan Domain Celery Application

scan-worker에서 사용하는 Celery 앱 인스턴스
"""

from celery import Celery

from domains._shared.celery.config import get_celery_settings

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
