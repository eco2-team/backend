from fastapi import APIRouter, Depends, HTTPException, status

from domains.scan.schemas.scan import (
    ClassificationRequest,
    ClassificationResponse,
    ScanCategory,
    ScanTask,
)
from domains.scan.services.scan import ScanService
from domains.scan.api.dependencies import get_current_user, UserInfo

router = APIRouter(prefix="/scan", tags=["scan"])


@router.post(
    "/classify",
    response_model=ClassificationResponse,
    summary="Submit waste image for classification",
)
async def classify(
    payload: ClassificationRequest,
    user: UserInfo = Depends(get_current_user),
    service: ScanService = Depends(),
):
    return await service.classify(payload, user.user_id)


@router.get(
    "/task/{task_id}",
    response_model=ScanTask,
    summary="Fetch classification task result",
)
async def task(task_id: str, service: ScanService = Depends()):
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
async def categories(service: ScanService = Depends()):
    return await service.categories()
