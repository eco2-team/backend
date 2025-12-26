"""My domain Celery tasks.

- save_my_character_task: 유저 캐릭터 DB 저장 (my.user_characters)
"""

from domains.my.tasks.sync_character import save_my_character_task

__all__ = [
    "save_my_character_task",
]
