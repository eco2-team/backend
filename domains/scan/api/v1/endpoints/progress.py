"""SSE Progress Streaming Endpoint.

Celery Events 기반 실시간 진행상황 + 최종 결과 전달.
task_id로 chain의 각 단계별 상태를 스트리밍합니다.

SSE 재접속 지원:
- 각 이벤트에 event_id 포함 (id: 필드)
- Last-Event-ID 헤더로 재접속 시 이어받기 가능
- Redis에 최근 이벤트 캐싱 (5분간 보관)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import AsyncGenerator

from fastapi import APIRouter, Header
from fastapi.responses import StreamingResponse

router = APIRouter(prefix="/scan", tags=["scan-progress"])

logger = logging.getLogger(__name__)

# Task 이름 → 단계 매핑 (4단계 Chain)
TASK_STEP_MAP = {
    "scan.vision": {"step": "vision", "progress": 25},
    "scan.rule": {"step": "rule", "progress": 50},
    "scan.answer": {"step": "answer", "progress": 75},
    "scan.reward": {"step": "reward", "progress": 100},
}

# SSE 이벤트 캐시 설정
SSE_EVENT_CACHE_TTL = 300  # 5분간 이벤트 보관
SSE_EVENT_CACHE_PREFIX = "sse:scan:events:"


def _get_redis_client():
    """Redis 클라이언트 가져오기 (lazy init).

    클러스터 내부: REDIS_HOST 환경변수 사용 (redis.redis.svc.cluster.local)
    로컬: REDIS_URL 환경변수 또는 기본값 사용
    """
    import redis

    # REDIS_URL이 명시적으로 설정된 경우 우선 사용
    redis_url = os.getenv("REDIS_URL")
    if redis_url:
        return redis.from_url(redis_url, decode_responses=True)

    # 클러스터 내부: REDIS_HOST로 URL 구성 (db=7 for SSE cache)
    redis_host = os.getenv("REDIS_HOST", "localhost")
    redis_port = os.getenv("REDIS_PORT", "6379")
    redis_db = os.getenv("REDIS_SSE_DB", "7")  # SSE 전용 DB

    return redis.from_url(
        f"redis://{redis_host}:{redis_port}/{redis_db}",
        decode_responses=True,
    )


@router.get(
    "/{task_id}/progress",
    summary="Stream task progress via SSE",
    response_class=StreamingResponse,
)
async def stream_progress(
    task_id: str,
    last_event_id: str | None = Header(None, alias="Last-Event-ID"),
) -> StreamingResponse:
    """Celery Events 기반 실시간 진행상황 + 최종 결과 스트리밍.

    클라이언트는 EventSource API로 연결하여 진행상황과 최종 결과를 수신합니다.

    재접속 지원:
        - 연결 끊김 후 재접속 시 Last-Event-ID 헤더 전송
        - 서버가 해당 ID 이후의 이벤트를 재전송

    Progress Events (id 포함):
        id: 1
        data: {"step": "vision", "status": "completed", "progress": 25}

    Args:
        task_id: Scan task identifier (chain의 첫 번째 task ID)
        last_event_id: 재접속 시 마지막으로 받은 이벤트 ID

    Returns:
        SSE 스트림 (text/event-stream)
    """
    return StreamingResponse(
        _event_generator(task_id, last_event_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # nginx buffering 비활성화
        },
    )


async def _event_generator(
    task_id: str, last_event_id: str | None = None
) -> AsyncGenerator[str, None]:
    """Celery Events를 수신하여 SSE 형식으로 변환.

    Celery Event Receiver를 별도 스레드에서 실행하고,
    asyncio Queue를 통해 이벤트를 전달받습니다.

    Args:
        task_id: Scan task ID
        last_event_id: 재접속 시 마지막으로 받은 이벤트 ID
    """
    from concurrent.futures import ThreadPoolExecutor

    from domains.scan.celery_app import celery_app

    # Redis 클라이언트 (이벤트 캐싱용)
    redis_client = None
    try:
        redis_client = _get_redis_client()
    except Exception as e:
        logger.warning(f"Redis 연결 실패, 이벤트 캐싱 비활성화: {e}")

    cache_key = f"{SSE_EVENT_CACHE_PREFIX}{task_id}"
    event_counter = 0

    # 재접속 시 캐시된 이벤트 재전송
    if last_event_id and redis_client:
        try:
            cached_events = redis_client.lrange(cache_key, 0, -1)
            last_id = int(last_event_id)

            for cached in cached_events:
                event_data = json.loads(cached)
                event_id = event_data.get("_event_id", 0)
                if event_id > last_id:
                    yield _format_sse_with_id(event_data, event_id)
                    event_counter = max(event_counter, event_id)

            logger.info(
                "SSE 재접속: 캐시된 이벤트 재전송",
                extra={"task_id": task_id, "last_event_id": last_id, "replayed": event_counter},
            )
        except Exception as e:
            logger.warning(f"캐시된 이벤트 재전송 실패: {e}")

    # 이벤트 전달용 Queue
    event_queue: asyncio.Queue[dict | None] = asyncio.Queue()
    loop = asyncio.get_event_loop()

    # 관련 task IDs 추적 (chain의 task들)
    chain_task_ids: set[str] = set()
    chain_task_ids.add(task_id)

    def on_task_sent(event: dict) -> None:
        _handle_event(event, "sent")

    def on_task_started(event: dict) -> None:
        _handle_event(event, "started")

    def on_task_succeeded(event: dict) -> None:
        _handle_event(event, "completed", result=event.get("result"))

    def on_task_failed(event: dict) -> None:
        _handle_event(event, "failed")

    def _handle_event(event: dict, status: str, result: dict | None = None) -> None:
        """이벤트 처리 및 Queue로 전달."""
        event_task_id = event.get("uuid", "")
        task_name = event.get("name", "")
        parent_id = event.get("parent_id")

        is_chain_task = (
            event_task_id == task_id
            or event_task_id in chain_task_ids
            or parent_id in chain_task_ids
        )

        if not is_chain_task:
            return

        chain_task_ids.add(event_task_id)

        step_info = TASK_STEP_MAP.get(task_name, {})
        if not step_info:
            return

        sse_data: dict = {
            "task_id": event_task_id,
            "step": step_info["step"],
            "status": status,
            "progress": step_info["progress"] if status == "completed" else 0,
        }

        # 마지막 단계(reward) 완료 시 최종 결과 포함
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
                "error": None,
            }

        loop.call_soon_threadsafe(event_queue.put_nowait, sse_data)

        if task_name == "scan.reward" and status in ("completed", "failed"):
            loop.call_soon_threadsafe(event_queue.put_nowait, None)

    def run_event_receiver() -> None:
        """Celery Event Receiver 실행 (별도 스레드)."""
        try:
            with celery_app.connection() as connection:
                recv = celery_app.events.Receiver(
                    connection,
                    handlers={
                        "task-sent": on_task_sent,
                        "task-started": on_task_started,
                        "task-succeeded": on_task_succeeded,
                        "task-failed": on_task_failed,
                    },
                )
                recv.capture(limit=None, timeout=60, wakeup=True)
        except Exception as e:
            logger.exception("Event receiver error", extra={"task_id": task_id, "error": str(e)})
            loop.call_soon_threadsafe(event_queue.put_nowait, None)

    # 초기 연결 메시지
    event_counter += 1
    yield _format_sse_with_id({"status": "connected", "task_id": task_id}, event_counter)

    # Event Receiver를 별도 스레드에서 실행
    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(run_event_receiver)

    try:
        timeout = 120
        start_time = asyncio.get_event_loop().time()

        while True:
            try:
                event = await asyncio.wait_for(event_queue.get(), timeout=1.0)

                if event is None:
                    logger.info("SSE stream completed", extra={"task_id": task_id})
                    break

                event_counter += 1

                # Redis에 이벤트 캐싱 (재접속 시 재전송용)
                if redis_client:
                    try:
                        event_with_id = {**event, "_event_id": event_counter}
                        redis_client.rpush(cache_key, json.dumps(event_with_id))
                        redis_client.expire(cache_key, SSE_EVENT_CACHE_TTL)
                    except Exception as e:
                        logger.warning(f"이벤트 캐싱 실패: {e}")

                yield _format_sse_with_id(event, event_counter)

                if event.get("step") == "reward" and event.get("status") in ("completed", "failed"):
                    break

            except asyncio.TimeoutError:
                elapsed = asyncio.get_event_loop().time() - start_time
                if elapsed > timeout:
                    logger.warning("SSE stream timeout", extra={"task_id": task_id})
                    event_counter += 1
                    yield _format_sse_with_id(
                        {"status": "timeout", "task_id": task_id}, event_counter
                    )
                    break

                # Keep-alive ping (SSE comment)
                yield ": keepalive\n\n"

    finally:
        future.cancel()
        executor.shutdown(wait=False)


def _format_sse_with_id(data: dict, event_id: int) -> str:
    """SSE 형식으로 포맷팅 (id 포함).

    SSE 표준 형식:
        id: <event_id>
        data: <json_data>
    """
    # _event_id는 내부용이므로 전송 시 제거
    data_clean = {k: v for k, v in data.items() if k != "_event_id"}
    return f"id: {event_id}\ndata: {json.dumps(data_clean)}\n\n"


def _format_sse(data: dict) -> str:
    """SSE 형식으로 포맷팅 (id 없음, 레거시 호환)."""
    return f"data: {json.dumps(data)}\n\n"
