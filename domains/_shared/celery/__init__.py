"""
Celery Shared Module

공통 Celery 설정 및 기반 Task 클래스 제공
"""

from domains._shared.celery.base_task import BaseTask, WebhookTask
from domains._shared.celery.config import CelerySettings, get_celery_settings

# DLQ 재처리 태스크 등록 (autodiscover_tasks는 tasks.py만 찾음)
# 각 worker가 이 모듈을 import할 때 자동으로 DLQ 태스크들이 등록됨
from domains._shared.celery import dlq_tasks as _dlq_tasks  # noqa: F401

__all__ = [
    "BaseTask",
    "WebhookTask",
    "CelerySettings",
    "get_celery_settings",
]
