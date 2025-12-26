"""Scan API endpoints.

DB 없이 로그 기반 추적 - EFK 파이프라인으로 수집.
"""

from fastapi import APIRouter

from domains.scan.api.dependencies import CurrentUser, ScanServiceDep
from domains.scan.schemas.scan import (
    ClassificationRequest,
    ClassificationResponse,
    ScanCategory,
)

router = APIRouter(prefix="/scan", tags=["scan"])


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

    비동기 처리가 필요한 경우 `/classify/async` 엔드포인트를 사용하세요.
    """
    return await service.classify_sync(payload, user.user_id)


@router.post(
    "/classify/async",
    response_model=ClassificationResponse,
    summary="Submit waste image for classification (async)",
)
async def classify_async(
    payload: ClassificationRequest,
    user: CurrentUser,
    service: ScanServiceDep,
) -> ClassificationResponse:
    """이미지를 분석하여 폐기물을 분류합니다 (비동기 처리).

    Celery Chain으로 비동기 처리를 시작하고 task_id를 즉시 반환합니다.
    응답 시간: 약 100ms

    결과는 SSE 엔드포인트 `/scan/{task_id}/progress`로 실시간 수신합니다.

    Returns:
        - task_id: SSE 연결에 사용할 task ID
        - status: "processing"
        - message: 안내 메시지
    """
    return await service.classify_async(payload, user.user_id)


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
