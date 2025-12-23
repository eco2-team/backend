"""
Celery Async Support Module

Worker에서 비동기 함수를 효율적으로 호출하기 위한 유틸리티.
- Event loop 재사용 (Worker당 1개)
- AsyncOpenAI connection pool 활용

Usage:
    from domains._shared.celery.async_support import run_async, init_event_loop

    # Worker 시작 시
    @worker_ready.connect
    def on_worker_ready(sender, **kwargs):
        init_event_loop()

    # Task에서
    @celery_app.task
    def my_task():
        result = run_async(some_async_function())
        return result
"""

from __future__ import annotations

import asyncio
import logging
from typing import Coroutine, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Worker별 공유 event loop
_event_loop: asyncio.AbstractEventLoop | None = None


def init_event_loop() -> None:
    """Worker 시작 시 event loop 초기화.

    worker_ready signal에서 호출해야 합니다.
    """
    global _event_loop
    if _event_loop is not None:
        logger.warning("Event loop already initialized, skipping")
        return

    _event_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_event_loop)
    logger.info("Shared event loop initialized for worker")


def shutdown_event_loop() -> None:
    """Worker 종료 시 event loop 정리.

    worker_shutdown signal에서 호출해야 합니다.
    """
    global _event_loop
    if _event_loop is None:
        return

    try:
        # 남은 task들 취소
        pending = asyncio.all_tasks(_event_loop)
        for task in pending:
            task.cancel()

        # 잠시 대기하여 취소 처리
        if pending:
            _event_loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))

        _event_loop.close()
        logger.info("Shared event loop closed")
    except Exception:
        logger.exception("Failed to close event loop cleanly")
    finally:
        _event_loop = None


def run_async(coro: Coroutine[None, None, T]) -> T:
    """공유 event loop에서 코루틴 실행.

    Celery task 내에서 비동기 함수를 호출할 때 사용합니다.

    Args:
        coro: 실행할 코루틴

    Returns:
        코루틴 실행 결과

    Raises:
        RuntimeError: event loop가 초기화되지 않은 경우

    Example:
        result = run_async(analyze_images_async(prompt, image_url))
    """
    global _event_loop

    if _event_loop is None:
        # Fallback: loop가 없으면 새로 생성 (비효율적, 경고 출력)
        logger.warning("Event loop not initialized, creating temporary loop")
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()

    return _event_loop.run_until_complete(coro)


def run_async_gather(*coros: Coroutine) -> list:
    """여러 코루틴을 병렬로 실행.

    동시에 여러 비동기 작업을 수행할 때 사용합니다.

    Args:
        *coros: 실행할 코루틴들

    Returns:
        각 코루틴의 결과 리스트

    Example:
        results = run_async_gather(
            analyze_images_async(prompt1, image1),
            analyze_images_async(prompt2, image2),
        )
    """
    return run_async(asyncio.gather(*coros))
