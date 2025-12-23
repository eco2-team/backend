"""Character domain Celery tasks.

캐릭터 보상 저장 관련 태스크:
- save_ownership_task: character.character_ownerships 저장 (character.reward 큐)

Note: scan_reward_task는 scan 도메인에서 처리 (domains/scan/tasks/reward.py)
      scan.reward에서 직접 이 task를 호출합니다.
"""

from domains.character.celery_app import celery_app
from domains.character.tasks.reward import save_ownership_task

__all__ = [
    "celery_app",
    "save_ownership_task",
]
