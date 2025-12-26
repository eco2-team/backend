"""SSE Stream 엔드포인트.

/api/v1/stream/{job_id}
- job_id에 대한 실시간 이벤트 스트림 제공
- Server-Sent Events (text/event-stream)
"""

import json
import logging
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException, Request
from sse_starlette.sse import EventSourceResponse

from core.broadcast_manager import SSEBroadcastManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/stream", tags=["SSE"])


async def event_generator(
    job_id: str,
    request: Request,
) -> AsyncGenerator[dict[str, str], None]:
    """SSE 이벤트 제너레이터.

    Args:
        job_id: Chain root task ID
        request: FastAPI Request (연결 상태 확인용)

    Yields:
        SSE 이벤트 딕셔너리 (event, data)
    """
    manager = await SSEBroadcastManager.get_instance()

    async for event in manager.subscribe(job_id):
        # 클라이언트 연결 해제 확인
        if await request.is_disconnected():
            logger.info(
                "sse_client_disconnected",
                extra={"job_id": job_id},
            )
            break

        event_type = event.get("type", "message")

        # keepalive
        if event_type == "keepalive":
            yield {
                "event": "keepalive",
                "data": json.dumps({"timestamp": event.get("timestamp", "")}),
            }
            continue

        # error
        if event_type == "error" or event.get("status") == "failed":
            yield {
                "event": "error",
                "data": json.dumps(event),
            }
            continue

        # stage 이벤트 (queued, vision, rule, answer, reward, done)
        stage = event.get("stage", "unknown")
        yield {
            "event": stage,
            "data": json.dumps(event),
        }


@router.get(
    "/{job_id}",
    summary="SSE 스트림 구독",
    description="job_id에 대한 실시간 이벤트 스트림을 제공합니다.",
    responses={
        200: {
            "description": "SSE 스트림",
            "content": {"text/event-stream": {}},
        },
        400: {"description": "잘못된 job_id"},
    },
)
async def stream_events(
    job_id: str,
    request: Request,
) -> EventSourceResponse:
    """SSE 스트림 엔드포인트.

    Args:
        job_id: Celery Chain root task ID (UUID)
        request: FastAPI Request

    Returns:
        EventSourceResponse (text/event-stream)

    Example:
        ```javascript
        const eventSource = new EventSource('/api/v1/stream/abc-123');
        eventSource.addEventListener('vision', (e) => {
            console.log('Vision 완료:', JSON.parse(e.data));
        });
        eventSource.addEventListener('done', (e) => {
            console.log('완료:', JSON.parse(e.data));
            eventSource.close();
        });
        ```
    """
    if not job_id or len(job_id) < 10:
        raise HTTPException(status_code=400, detail="Invalid job_id")

    logger.info(
        "sse_stream_started",
        extra={
            "job_id": job_id,
            "client_ip": request.client.host if request.client else "unknown",
        },
    )

    return EventSourceResponse(
        event_generator(job_id, request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Nginx 버퍼링 비활성화
        },
    )


@router.get("/health", include_in_schema=False)
async def health() -> dict[str, str]:
    """헬스 체크."""
    return {"status": "ok"}
