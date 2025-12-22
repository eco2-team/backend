"""Character domain MQ consumers."""

from domains.character.consumers.reward import (
    celery_app,
    persist_reward_task,
    reward_consumer_task,
    save_my_character_task,
    save_ownership_task,
    scan_reward_task,
)

# Legacy: gRPC 방식 (deprecated, 직접 DB 저장으로 전환됨)
from domains.character.consumers.sync_my import sync_to_my_task

__all__ = [
    "celery_app",
    "persist_reward_task",
    "reward_consumer_task",
    "save_my_character_task",
    "save_ownership_task",
    "scan_reward_task",
    "sync_to_my_task",  # deprecated
]
