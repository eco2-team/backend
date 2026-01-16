"""Celery Tasks for News Collection.

Celery Beat에 의해 주기적으로 호출되는 뉴스 수집 태스크.
gevent 몽키패칭 호환을 위해 동기 코드로 작성.
"""

from __future__ import annotations

import logging

from celery import Task
from celery.signals import worker_shutdown

from info_worker.setup.celery import celery_app
from info_worker.setup.dependencies import (
    cleanup,
    create_collect_news_command,
    create_collect_news_command_newsdata_only,
)

logger = logging.getLogger(__name__)


# ============================================================
# Worker Lifecycle
# ============================================================
@worker_shutdown.connect
def on_worker_shutdown(**kwargs):
    """Worker 종료 시 리소스 정리."""
    logger.info("Worker shutting down, cleaning up resources...")
    cleanup()
    logger.info("Cleanup completed")


# ============================================================
# Celery Tasks
# ============================================================
@celery_app.task(
    bind=True,
    name="info.collect_news",
    queue="info.collect_news",
    max_retries=2,
    soft_time_limit=120,
    time_limit=180,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=60,
)
def collect_news_task(
    self: Task,
    category: str = "all",
    source: str | None = None,
) -> dict:
    """뉴스 수집 태스크 (전체 소스).

    Celery Beat에 의해 5분 주기로 호출.
    gevent 몽키패칭이 적용되어 동기 코드도 협력적 멀티태스킹.

    Args:
        category: 수집할 카테고리 ("all", "environment", "energy", "ai")
        source: 특정 소스만 사용 (선택)

    Returns:
        수집 결과
    """
    logger.info(
        "Starting collect_news_task",
        extra={"category": category, "source": source, "task_id": self.request.id},
    )

    try:
        command = create_collect_news_command()
        result = command.execute(category=category)

        result_dict = {
            "status": "success",
            "fetched": result.fetched,
            "unique": result.unique,
            "saved": result.saved,
            "cached": result.cached,
            "with_images": result.with_images,
            "category": result.category,
        }

        logger.info(
            "collect_news_task completed",
            extra={"result": result_dict, "task_id": self.request.id},
        )
        return result_dict

    except Exception as e:
        logger.exception(
            "collect_news_task failed",
            extra={"error": str(e), "task_id": self.request.id},
        )
        raise


@celery_app.task(
    bind=True,
    name="info.collect_news_newsdata",
    queue="info.collect_news",
    max_retries=2,
    soft_time_limit=60,
    time_limit=90,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=60,
)
def collect_news_newsdata_task(
    self: Task,
    category: str = "all",
) -> dict:
    """NewsData.io 전용 뉴스 수집 태스크.

    Celery Beat에 의해 30분 주기로 호출.
    Rate Limit 대응: 30분 × 48회 = 1,440분 < 200 API 호출/일.

    Args:
        category: 수집할 카테고리

    Returns:
        수집 결과
    """
    logger.info(
        "Starting collect_news_newsdata_task",
        extra={"category": category, "task_id": self.request.id},
    )

    try:
        command = create_collect_news_command_newsdata_only()
        result = command.execute(category=category)

        result_dict = {
            "status": "success",
            "source": "newsdata",
            "fetched": result.fetched,
            "unique": result.unique,
            "saved": result.saved,
            "cached": result.cached,
            "with_images": result.with_images,
            "category": result.category,
        }

        logger.info(
            "collect_news_newsdata_task completed",
            extra={"result": result_dict, "task_id": self.request.id},
        )
        return result_dict

    except Exception as e:
        logger.exception(
            "collect_news_newsdata_task failed",
            extra={"error": str(e), "task_id": self.request.id},
        )
        raise
