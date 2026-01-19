"""SSE Stream 엔드포인트.

GET /api/v1/stream?job_id=xxx
- job_id에 대한 실시간 이벤트 스트림 제공
- Server-Sent Events (text/event-stream)
- Istio sticky session으로 동일 pod 라우팅
"""

import json
import logging
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException, Query, Request
from sse_starlette.sse import EventSourceResponse

from sse_gateway.core.broadcast_manager import SSEBroadcastManager

logger = logging.getLogger(__name__)

router = APIRouter(tags=["SSE"])


async def event_generator(
    job_id: str,
    request: Request,
    domain: str = "scan",
    last_token_seq: int = 0,
) -> AsyncGenerator[dict[str, str], None]:
    """SSE 이벤트 제너레이터.

    Args:
        job_id: Chain root task ID
        request: FastAPI Request (연결 상태 확인용)
        domain: 서비스 도메인 (scan, chat)
        last_token_seq: 마지막으로 받은 토큰 seq (Token v2 복구용)

    Yields:
        SSE 이벤트 딕셔너리 (event, data)
    """
    manager = await SSEBroadcastManager.get_instance()

    # Token v2: 재연결 시 Token 복구 (chat 도메인만)
    if domain == "chat":
        if last_token_seq > 0:
            # 마지막 seq 이후 토큰 catch-up
            async for token_event in manager.catch_up_tokens(job_id, last_token_seq):
                if await request.is_disconnected():
                    break
                logger.info(
                    "sse_token_sent",
                    extra={
                        "job_id": job_id,
                        "seq": token_event.get("seq"),
                    },
                )
                yield {
                    "event": "token",
                    "data": json.dumps(token_event),
                }
        else:
            # 새 연결: Token State에서 누적 텍스트 복구
            recovery_event = await manager.get_token_recovery_event(job_id)
            if recovery_event:
                logger.info(
                    "sse_token_recovery_sent",
                    extra={
                        "job_id": job_id,
                        "last_seq": recovery_event.get("last_seq"),
                    },
                )
                yield {
                    "event": "token_recovery",
                    "data": json.dumps(recovery_event),
                }

    async for event in manager.subscribe(job_id, domain=domain):
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
            logger.warning(
                "sse_error_sent",
                extra={
                    "job_id": job_id,
                    "event": event,
                },
            )
            yield {
                "event": "error",
                "data": json.dumps(event),
            }
            continue

        # stage 이벤트 (queued, vision, rule, answer, reward, done)
        stage = event.get("stage", "unknown")
        logger.info(
            "sse_event_sent",
            extra={
                "job_id": job_id,
                "event_type": stage,
                "seq": event.get("seq"),
            },
        )
        yield {
            "event": stage,
            "data": json.dumps(event),
        }


@router.get(
    "/stream",
    summary="SSE 스트림 구독 (레거시)",
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
    request: Request,
    job_id: str = Query(..., description="작업 ID (UUID)", min_length=10),
) -> EventSourceResponse:
    """SSE 스트림 엔드포인트 (레거시).

    Args:
        request: FastAPI Request
        job_id: Celery Chain root task ID (UUID) - 쿼리 파라미터

    Returns:
        EventSourceResponse (text/event-stream)

    Example:
        ```javascript
        const eventSource = new EventSource('/api/v1/stream?job_id=abc-123');
        eventSource.addEventListener('vision', (e) => {
            console.log('Vision 완료:', JSON.parse(e.data));
        });
        eventSource.addEventListener('done', (e) => {
            console.log('완료:', JSON.parse(e.data));
            eventSource.close();
        });
        ```
    """
    if not job_id:
        raise HTTPException(status_code=400, detail="job_id is required")

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
        },
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# RESTful SSE 엔드포인트: /{service}/{job_id}/events
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


SUPPORTED_DOMAINS = {"scan", "chat"}


@router.get(
    "/{service}/{job_id}/events",
    summary="SSE 스트림 구독 (RESTful)",
    description="서비스별 job_id에 대한 실시간 이벤트 스트림을 제공합니다.",
    responses={
        200: {
            "description": "SSE 스트림",
            "content": {"text/event-stream": {}},
        },
        400: {"description": "잘못된 요청"},
    },
)
async def stream_events_restful(
    request: Request,
    service: str,
    job_id: str,
    last_token_seq: int = Query(
        default=0,
        description="마지막으로 받은 토큰 seq (재연결 시 복구용, chat 전용)",
    ),
) -> EventSourceResponse:
    """RESTful SSE 스트림 엔드포인트.

    Args:
        request: FastAPI Request
        service: 서비스명 (scan, chat)
        job_id: 작업 ID (UUID)
        last_token_seq: 마지막으로 받은 토큰 seq (Token v2 복구용)

    Returns:
        EventSourceResponse (text/event-stream)

    Example:
        ```javascript
        // scan 서비스
        const eventSource = new EventSource('/api/v1/scan/abc-123/events');

        // chat 서비스
        const eventSource = new EventSource('/api/v1/chat/xyz-456/events');

        // chat 재연결 (Token 복구)
        const eventSource = new EventSource('/api/v1/chat/xyz-456/events?last_token_seq=1050');

        eventSource.addEventListener('token_recovery', (e) => {
            const data = JSON.parse(e.data);
            console.log('Token 복구:', data.accumulated);  // 누적 텍스트
        });

        eventSource.addEventListener('token', (e) => {
            const data = JSON.parse(e.data);
            console.log('Token:', data.content);  // 개별 토큰
        });

        eventSource.addEventListener('done', (e) => {
            console.log('완료:', JSON.parse(e.data));
            eventSource.close();
        });
        ```
    """
    if not job_id or len(job_id) < 10:
        raise HTTPException(status_code=400, detail="유효하지 않은 job_id입니다")

    if service not in SUPPORTED_DOMAINS:
        raise HTTPException(
            status_code=400,
            detail=f"지원하지 않는 서비스입니다. (지원: {', '.join(SUPPORTED_DOMAINS)})",
        )

    logger.info(
        "sse_stream_started",
        extra={
            "service": service,
            "job_id": job_id,
            "last_token_seq": last_token_seq,
            "client_ip": request.client.host if request.client else "unknown",
        },
    )

    return EventSourceResponse(
        event_generator(job_id, request, domain=service, last_token_seq=last_token_seq),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )
