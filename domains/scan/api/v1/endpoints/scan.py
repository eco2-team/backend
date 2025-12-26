"""Scan API endpoints.

DB 없이 로그 기반 추적 - EFK 파이프라인으로 수집.

v2 아키텍처:
- POST /api/v1/scan → 비동기 제출, job_id 반환
- GET /api/v1/stream?job_id=xxx → SSE 스트리밍 (sse-gateway)
- GET /api/v1/scan/result/{job_id} → 최종 결과 조회
"""

import logging
from uuid import uuid4

from celery import chain
from fastapi import APIRouter, HTTPException

from domains._shared.events import get_sync_redis_client, publish_stage_event
from domains.scan.api.dependencies import CurrentUser, ScanServiceDep
from domains.scan.schemas.scan import (
    ClassificationRequest,
    ClassificationResponse,
    ScanCategory,
    ScanSubmitResponse,
)
from domains.scan.tasks.answer import answer_task
from domains.scan.tasks.reward import scan_reward_task
from domains.scan.tasks.rule import rule_task
from domains.scan.tasks.vision import vision_task

router = APIRouter(prefix="/scan", tags=["scan"])
logger = logging.getLogger(__name__)


@router.post(
    "",
    response_model=ScanSubmitResponse,
    summary="Submit waste image for async classification",
)
async def submit_scan(
    payload: ClassificationRequest,
    user: CurrentUser,
) -> ScanSubmitResponse:
    """이미지 분류 작업을 비동기로 제출합니다.

    클라이언트 흐름:
    1. 이 엔드포인트 호출 → job_id, stream_url, result_url 수신
    2. stream_url로 SSE 연결 → 실시간 진행상황 수신
    3. 완료 후 result_url로 최종 결과 조회

    Returns:
        ScanSubmitResponse: job_id, stream_url, result_url
    """
    image_url = str(payload.image_url) if payload.image_url else None
    if not image_url:
        raise HTTPException(status_code=400, detail="image_url is required")

    job_id = str(uuid4())
    user_id = str(user.user_id)
    user_input = payload.user_input or "이 폐기물을 어떻게 분리배출해야 하나요?"

    # Redis Streams에 queued 이벤트 발행
    redis_client = get_sync_redis_client()
    publish_stage_event(
        redis_client=redis_client,
        job_id=job_id,
        stage="queued",
        status="started",
        progress=0,
    )

    # Celery Chain 비동기 발행
    pipeline = chain(
        vision_task.s(job_id, user_id, image_url, user_input),
        rule_task.s(),
        answer_task.s(),
        scan_reward_task.s(),
    )
    pipeline.apply_async(task_id=job_id)

    logger.info(
        "scan_submitted",
        extra={
            "job_id": job_id,
            "user_id": user_id,
            "image_url": image_url,
        },
    )

    return ScanSubmitResponse(
        job_id=job_id,
        stream_url=f"/api/v1/stream?job_id={job_id}",
        result_url=f"/api/v1/scan/result/{job_id}",
        status="queued",
    )


@router.post(
    "/classify",
    response_model=ClassificationResponse,
    summary="Submit waste image for classification (sync)",
)
async def classify(
    payload: ClassificationRequest,
    user: CurrentUser,
    service: ScanServiceDep,
) -> ClassificationResponse:
    """이미지를 분석하여 폐기물을 분류합니다 (동기 처리).

    동기적으로 AI 파이프라인을 실행하고 결과를 즉시 반환합니다.
    응답 시간: 약 3-5초

    실시간 진행상황이 필요한 경우 `/classify/completion` 엔드포인트를 사용하세요.
    """
    return await service.classify_sync(payload, user.user_id)


@router.get(
    "/result/{job_id}",
    response_model=ClassificationResponse,
    summary="Get scan result by job_id",
)
async def get_result(
    job_id: str,
    service: ScanServiceDep,
) -> ClassificationResponse:
    """작업 ID로 분류 결과를 조회합니다.

    Redis Cache에서 결과를 조회합니다.
    결과가 없으면 404를 반환합니다.
    """
    result = await service.get_result(job_id)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"Result not found for job_id: {job_id}",
        )
    return result


@router.get(
    "/categories",
    response_model=list[ScanCategory],
    summary="Supported waste categories",
)
async def categories(service: ScanServiceDep) -> list[ScanCategory]:
    """지원하는 폐기물 카테고리 목록을 반환합니다."""
    return await service.categories()


@router.get(
    "/metrics",
    summary="Service metrics summary",
)
async def metrics(service: ScanServiceDep) -> dict:
    """서비스 메트릭 요약 (상세는 /metrics 또는 Kibana)."""
    return await service.metrics()
