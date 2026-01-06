"""Celery Tasks - 파이프라인 진입점.

Clean Architecture:
- Task는 Presentation Layer (진입점)
- 실제 로직은 Application Layer (Steps)에서 처리
- domains 의존성 제거됨
"""

from scan_worker.presentation.tasks.answer_task import answer_task
from scan_worker.presentation.tasks.reward_task import reward_task
from scan_worker.presentation.tasks.rule_task import rule_task
from scan_worker.presentation.tasks.vision_task import vision_task

__all__ = [
    "vision_task",
    "rule_task",
    "answer_task",
    "reward_task",
]
