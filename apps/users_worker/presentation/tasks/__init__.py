"""Celery Tasks."""

from apps.users_worker.presentation.tasks.character_task import save_characters_task

__all__ = ["save_characters_task"]
