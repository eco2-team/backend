"""Celery tasks."""

from info_worker.presentation.tasks.collect_news_task import (
    collect_news_task,
    collect_news_newsdata_task,
)

__all__ = ["collect_news_task", "collect_news_newsdata_task"]
