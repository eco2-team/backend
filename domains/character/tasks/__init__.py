"""Character domain Celery tasks.

캐릭터 관련 태스크:
- match_character_task: 캐릭터 매칭 (character.match 큐) - 로컬 캐시 사용
- save_ownership_task: character.character_ownerships 저장 (character.reward 큐)

Note: scan.reward에서 character.match를 동기 호출하여 매칭 결과를 받습니다.
"""

from domains.character.celery_app import celery_app
from domains.character.tasks.match import match_character_task
from domains.character.tasks.reward import save_ownership_task

__all__ = [
    "celery_app",
    "match_character_task",
    "save_ownership_task",
]
