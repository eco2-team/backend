"""Scan API endpoints."""

from fastapi import APIRouter, HTTPException, status

from domains.scan.api.dependencies import CurrentUser, ScanServiceDep
from domains.scan.schemas.scan import (
    ClassificationRequest,
    ClassificationResponse,
    ScanCategory,
    ScanTask,
)

router = APIRouter(prefix="/scan", tags=["scan"])


@router.post(
    "/classify",
    response_model=ClassificationResponse,
    summary="Submit waste image for classification",
)
async def classify(
    payload: ClassificationRequest,
    user: CurrentUser,
    service: ScanServiceDep,
) -> ClassificationResponse:
    """이미지를 분석하여 폐기물을 분류합니다."""
    return await service.classify(payload, user.user_id)


@router.get(
    "/task/{task_id}",
    response_model=ScanTask,
    summary="Fetch classification task result",
)
async def task(task_id: str, service: ScanServiceDep) -> ScanTask:
    """태스크 ID로 분류 결과를 조회합니다."""
    try:
        return await service.task(task_id)
    except LookupError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"task {task_id} not found",
        )


@router.get(
    "/categories",
    response_model=list[ScanCategory],
    summary="Supported waste categories",
)
async def categories(service: ScanServiceDep) -> list[ScanCategory]:
    """지원하는 폐기물 카테고리 목록을 반환합니다."""
    return await service.categories()
