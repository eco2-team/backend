"""Scan Completion SSE Streaming Endpoint.

POST 요청에서 직접 SSE 스트림을 반환하는 Stateless 방식.
OpenAI/Anthropic 스트리밍 API 패턴과 동일.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import AsyncGenerator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from domains.scan.api.dependencies import CurrentUser, ScanServiceDep
from domains.scan.schemas.scan import ClassificationRequest

router = APIRouter(prefix="/scan", tags=["scan-completion"])

logger = logging.getLogger(__name__)

# Task 이름 → 단계 매핑 (4단계 Chain)
# prev_progress: started 상태일 때의 progress (이전 단계 완료 값)
TASK_STEP_MAP = {
    "scan.vision": {"step": "vision", "progress": 25, "prev_progress": 0},
    "scan.rule": {"step": "rule", "progress": 50, "prev_progress": 25},
    "scan.answer": {"step": "answer", "progress": 75, "prev_progress": 50},
    "scan.reward": {"step": "reward", "progress": 100, "prev_progress": 75},
}


@router.post(
    "/classify/completion",
    summary="Classify waste image with SSE streaming",
    response_class=StreamingResponse,
)
async def classify_completion(
    payload: ClassificationRequest,
    user: CurrentUser,
    service: ScanServiceDep,
) -> StreamingResponse:
    """이미지를 분석하여 폐기물을 분류합니다 (SSE 스트리밍).

    단일 POST 요청에서 SSE 스트림으로 진행상황과 최종 결과를 반환합니다.
    OpenAI/Anthropic streaming API와 동일한 패턴입니다.

    SSE Events:
        - started: 작업 시작 (task_id 포함)
        - progress: 각 단계 진행상황 (vision, rule, answer, reward)
        - completed: 최종 결과 포함
        - error: 에러 발생 시

    Example:
        ```
        data: {"status": "started", "task_id": "xxx"}
        data: {"step": "vision", "status": "completed", "progress": 25}
        data: {"step": "rule", "status": "completed", "progress": 50}
        data: {"step": "answer", "status": "completed", "progress": 75}
        data: {"step": "reward", "status": "completed", "progress": 100, "result": {...}}
        ```
    """
    return StreamingResponse(
        _completion_generator(payload, user, service),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # nginx buffering 비활성화
        },
    )


async def _completion_generator(
    payload: ClassificationRequest,
    user: CurrentUser,
    service: ScanServiceDep,
) -> AsyncGenerator[str, None]:
    """SSE 스트림 생성기.

    1. Task 시작 (chain.apply_async)
    2. Celery Events 수신하여 진행상황 스트리밍
    3. 최종 결과 전송 후 종료
    """
    from concurrent.futures import ThreadPoolExecutor
    from uuid import uuid4

    from celery import chain

    from domains.character.consumers.reward import scan_reward_task
    from domains.scan.celery_app import celery_app
    from domains.scan.tasks.answer import answer_task
    from domains.scan.tasks.rule import rule_task
    from domains.scan.tasks.vision import vision_task

    # 요청 검증
    image_url = str(payload.image_url) if payload.image_url else None
    if not image_url:
        yield _format_sse({"status": "error", "error": "IMAGE_URL_REQUIRED"})
        return

    # Task ID 생성
    task_id = str(uuid4())
    user_id = str(user.user_id)

    logger.info(
        "completion_stream_started",
        extra={
            "event_type": "completion_started",
            "task_id": task_id,
            "user_id": user_id,
            "image_url": image_url,
        },
    )

    # 1. Started 이벤트 전송
    yield _format_sse({"status": "started", "task_id": task_id})

    # 2. Celery Chain 시작 (SSE 연결 후 시작!)
    try:
        first_task = vision_task.s(task_id, user_id, image_url, payload.user_input).set(
            task_id=task_id
        )

        pipeline = chain(
            first_task,
            rule_task.s(),
            answer_task.s(),
            scan_reward_task.s(),
        )
        pipeline.apply_async()

        logger.info(
            "completion_chain_dispatched",
            extra={
                "event_type": "chain_dispatched",
                "task_id": task_id,
                "user_id": user_id,
            },
        )
    except Exception as e:
        logger.exception("completion_chain_failed", extra={"task_id": task_id})
        yield _format_sse({"status": "error", "error": str(e)})
        return

    # 3. Celery Events 수신 및 스트리밍
    event_queue: asyncio.Queue[dict | None] = asyncio.Queue()
    loop = asyncio.get_event_loop()

    # Chain task IDs 추적
    chain_task_ids: set[str] = {task_id}
    task_name_map: dict[str, str] = {}

    def _handle_event(event: dict, status: str, result: dict | None = None) -> None:
        """Celery 이벤트 처리."""
        event_task_id = event.get("uuid", "")
        task_name = event.get("name", "")
        root_id = event.get("root_id")
        parent_id = event.get("parent_id")

        # root_id로 chain 매칭
        is_chain_task = (
            root_id == task_id
            or event_task_id == task_id
            or event_task_id in chain_task_ids
            or parent_id in chain_task_ids
        )

        if not is_chain_task:
            return

        chain_task_ids.add(event_task_id)

        # task name 매핑
        if task_name:
            task_name_map[event_task_id] = task_name
        else:
            task_name = task_name_map.get(event_task_id, "")

        step_info = TASK_STEP_MAP.get(task_name, {})
        if not step_info:
            return

        # progress 계산: completed면 해당 단계 완료 값, started면 이전 단계 완료 값
        progress = (
            step_info["progress"] if status == "completed" else step_info.get("prev_progress", 0)
        )

        sse_data: dict = {
            "step": step_info["step"],
            "status": status,
            "progress": progress,
        }

        # reward 완료 시 최종 결과 포함
        if task_name == "scan.reward" and status == "completed" and result:
            sse_data["result"] = {
                "task_id": result.get("task_id"),
                "status": "completed",
                "message": "classification completed",
                "pipeline_result": {
                    "classification_result": result.get("classification_result"),
                    "disposal_rules": result.get("disposal_rules"),
                    "final_answer": result.get("final_answer"),
                },
                "reward": result.get("reward"),
            }

        loop.call_soon_threadsafe(event_queue.put_nowait, sse_data)

        if task_name == "scan.reward" and status in ("completed", "failed"):
            loop.call_soon_threadsafe(event_queue.put_nowait, None)

    def on_task_started(event: dict) -> None:
        _handle_event(event, "started")

    def on_task_succeeded(event: dict) -> None:
        _handle_event(event, "completed", result=event.get("result"))

    def on_task_failed(event: dict) -> None:
        _handle_event(event, "failed")

    def run_event_receiver() -> None:
        """Celery Event Receiver (별도 스레드)."""
        try:
            with celery_app.connection() as connection:
                recv = celery_app.events.Receiver(
                    connection,
                    handlers={
                        "task-started": on_task_started,
                        "task-succeeded": on_task_succeeded,
                        "task-failed": on_task_failed,
                    },
                )
                recv.capture(limit=None, timeout=120, wakeup=True)
        except Exception as e:
            logger.exception("event_receiver_error", extra={"task_id": task_id, "error": str(e)})
            loop.call_soon_threadsafe(event_queue.put_nowait, None)

    # Event Receiver 시작
    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(run_event_receiver)

    try:
        timeout = 120
        start_time = asyncio.get_event_loop().time()

        while True:
            try:
                event = await asyncio.wait_for(event_queue.get(), timeout=1.0)

                if event is None:
                    logger.info("completion_stream_ended", extra={"task_id": task_id})
                    break

                yield _format_sse(event)

                if event.get("step") == "reward" and event.get("status") in ("completed", "failed"):
                    break

            except asyncio.TimeoutError:
                elapsed = asyncio.get_event_loop().time() - start_time

                if elapsed > timeout:
                    logger.warning("completion_stream_timeout", extra={"task_id": task_id})
                    yield _format_sse({"status": "timeout", "task_id": task_id})
                    break

                # Keep-alive
                yield ": keepalive\n\n"

    finally:
        future.cancel()
        executor.shutdown(wait=False)


def _format_sse(data: dict) -> str:
    """SSE 형식으로 포맷팅."""
    return f"data: {json.dumps(data)}\n\n"
