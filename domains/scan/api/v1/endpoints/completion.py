"""Scan Completion SSE Streaming Endpoint.

POST 요청에서 직접 SSE 스트림을 반환하는 Stateless 방식.
OpenAI/Anthropic 스트리밍 API 패턴과 동일.

v2: Redis Streams 기반 이벤트 소싱
- Celery Events (RabbitMQ) → Redis Streams
- SSE:RabbitMQ 연결 폭발 문제 해결
- 참고: docs/blogs/async/24-redis-streams-sse-migration.md
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, AsyncGenerator
from uuid import uuid4

from celery import chain
from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from domains._shared.events import (
    get_async_redis_client,
    get_sync_redis_client,
    publish_stage_event,
    subscribe_events,
)
from domains.scan.api.dependencies import CurrentUser, ScanServiceDep
from domains.scan.metrics import (
    SSE_CHAIN_DURATION,
    SSE_CONNECTIONS_ACTIVE,
    SSE_REQUESTS_TOTAL,
    SSE_STAGE_DURATION,
    SSE_TTFB,
)
from domains.scan.schemas.scan import ClassificationRequest
from domains.scan.tasks.answer import answer_task
from domains.scan.tasks.reward import scan_reward_task
from domains.scan.tasks.rule import rule_task
from domains.scan.tasks.vision import vision_task

router = APIRouter(prefix="/scan", tags=["scan-completion"])

logger = logging.getLogger(__name__)


# Stage → progress 매핑
STAGE_PROGRESS_MAP = {
    "queued": 0,
    "vision": 25,
    "rule": 50,
    "answer": 75,
    "reward": 100,
    "done": 100,
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

    v2 변경사항:
        - Celery Events → Redis Streams로 이벤트 소싱 변경
        - RabbitMQ 연결 폭발 문제 해결 (SSE:RabbitMQ 1:21 → 0)

    SSE Events:
        - event: stage (진행 상황)
          data: {"step": "vision", "status": "started|completed", "progress": 25}

        - event: ready (완료)
          data: {"step": "done", "result": {...}, "result_url": "/result/xxx"}

        - event: error (오류)
          data: {"error": "...", "message": "..."}

    Example:
        ```
        event: stage
        data: {"step": "queued", "status": "started", "progress": 0, "job_id": "xxx"}

        event: stage
        data: {"step": "vision", "status": "started", "progress": 0}

        event: stage
        data: {"step": "vision", "status": "completed", "progress": 25}

        ...

        event: ready
        data: {"step": "done", "result": {...}, "result_url": "/result/xxx"}
        ```
    """
    return StreamingResponse(
        _completion_generator_v2(payload, user, service),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # nginx buffering 비활성화
        },
    )


async def _completion_generator_v2(
    payload: ClassificationRequest,
    user: CurrentUser,
    service: ScanServiceDep,
) -> AsyncGenerator[str, None]:
    """SSE 스트림 생성기 (v2: Redis Streams 기반).

    핵심 원칙: "구독 먼저, 발행 나중"
    1. Redis Streams 구독 시작
    2. queued 이벤트 발행 (구독 후)
    3. Celery Chain 발행
    4. Streams 이벤트 → SSE 전송
    5. done 이벤트 수신 시 종료
    """
    # 메트릭: 활성 연결 수 증가
    SSE_CONNECTIONS_ACTIVE.inc()
    chain_start_time = time.time()
    final_status = "success"
    stage_start_times: dict[str, float] = {}

    # 요청 검증
    image_url = str(payload.image_url) if payload.image_url else None
    if not image_url:
        SSE_CONNECTIONS_ACTIVE.dec()
        SSE_REQUESTS_TOTAL.labels(status="failed").inc()
        yield _format_sse({"error": "IMAGE_URL_REQUIRED"}, event_type="error")
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
            "version": "v2_redis_streams",
        },
    )

    try:
        # 1. Redis 클라이언트 획득
        redis_client = await get_async_redis_client()
        sync_redis = get_sync_redis_client()

        # 2. queued 이벤트 발행 (구독 전에 발행해도 리플레이로 수신 가능)
        publish_stage_event(sync_redis, task_id, "queued", "started", progress=0)

        # 3. 첫 SSE 이벤트 전송 (즉시)
        yield _format_sse(
            {
                "step": "queued",
                "status": "started",
                "progress": 0,
                "job_id": task_id,
            },
            event_type="stage",
        )

        # TTFB 메트릭
        ttfb = time.time() - chain_start_time
        SSE_TTFB.observe(ttfb)

        # 4. Celery Chain 발행
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
            yield _format_sse(
                {"error": str(e), "message": "Chain dispatch failed"},
                event_type="error",
            )
            final_status = "failed"
            return

        # 5. Redis Streams 구독 루프
        async for event in subscribe_events(redis_client, task_id):
            # keepalive 이벤트
            if event.get("type") == "keepalive":
                yield ": keepalive\n\n"
                continue

            # 에러 이벤트
            if event.get("type") == "error":
                logger.error(
                    "subscribe_events_error",
                    extra={"task_id": task_id, "error": event.get("error")},
                )
                yield _format_sse(event, event_type="error")
                final_status = "failed"
                break

            stage = event.get("stage", "")
            status = event.get("status", "")
            progress = event.get("progress") or STAGE_PROGRESS_MAP.get(stage, 0)

            # 스테이지별 시간 추적
            if status == "started":
                stage_start_times[stage] = time.time()
            elif status == "completed" and stage in stage_start_times:
                duration = time.time() - stage_start_times[stage]
                SSE_STAGE_DURATION.labels(stage=stage).observe(duration)
                logger.info(
                    "stage_completed",
                    extra={
                        "task_id": task_id,
                        "stage": stage,
                        "duration_seconds": round(duration, 3),
                    },
                )

            # SSE 이벤트 구성
            sse_data: dict[str, Any] = {
                "step": stage,
                "status": status,
                "progress": progress,
            }

            # done 이벤트 (파이프라인 완료)
            if stage == "done":
                sse_data["result"] = event.get("result")
                sse_data["result_url"] = f"/api/v1/scan/result/{task_id}"
                yield _format_sse(sse_data, event_type="ready")
                logger.info("completion_stream_done", extra={"task_id": task_id})
                break

            # reward 완료 시 결과 포함
            if stage == "reward" and status == "completed":
                sse_data["result"] = event.get("result")

            # 일반 stage 이벤트
            yield _format_sse(sse_data, event_type="stage")

            # 실패 시 종료
            if status == "failed":
                final_status = "failed"
                break

    except Exception as e:
        logger.exception("completion_stream_error", extra={"task_id": task_id})
        yield _format_sse(
            {"error": str(e), "message": "Stream error"},
            event_type="error",
        )
        final_status = "error"

    finally:
        # 메트릭 기록
        chain_duration = time.time() - chain_start_time
        SSE_CHAIN_DURATION.observe(chain_duration)
        SSE_REQUESTS_TOTAL.labels(status=final_status).inc()
        SSE_CONNECTIONS_ACTIVE.dec()

        logger.info(
            "completion_stream_finished",
            extra={
                "task_id": task_id,
                "status": final_status,
                "duration_seconds": round(chain_duration, 3),
                "version": "v2_redis_streams",
            },
        )


def _format_sse(data: dict, event_type: str = "message") -> str:
    """SSE 형식으로 포맷팅.

    Args:
        data: 이벤트 데이터
        event_type: SSE 이벤트 타입 (stage, ready, error, message)

    Returns:
        SSE 형식 문자열
    """
    return f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
