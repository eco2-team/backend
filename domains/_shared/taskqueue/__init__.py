"""Shared Task Queue module for async task processing.

이 모듈은 RabbitMQ + Celery 기반 비동기 태스크 처리를 위한 공통 구성요소를 제공합니다.

Usage:
    from domains._shared.taskqueue import celery_app, TaskState, TaskStatus, TaskStep

Components:
    - celery_app: Celery 애플리케이션 인스턴스
    - TaskState: 태스크 상태 관리 클래스
    - TaskStatus, TaskStep: 상태/단계 Enum
"""

from domains._shared.taskqueue.app import celery_app
from domains._shared.taskqueue.state import TaskState, TaskStatus, TaskStep

__all__ = [
    "celery_app",
    "TaskState",
    "TaskStatus",
    "TaskStep",
]
