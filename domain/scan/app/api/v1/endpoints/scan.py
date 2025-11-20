from fastapi import APIRouter, Depends

from app.schemas.scan import (
    ClassificationRequest,
    ClassificationResponse,
    ScanCategory,
    ScanTask,
)
from app.services.scan import ScanService

router = APIRouter(prefix="/scan", tags=["scan"])


@router.post(
    "/classify",
    response_model=ClassificationResponse,
    summary="Submit waste image for classification",
)
async def classify(
    payload: ClassificationRequest,
    service: ScanService = Depends(),
):
    return await service.classify(payload)


@router.get(
    "/task/{task_id}",
    response_model=ScanTask,
    summary="Fetch classification task result",
)
async def task(task_id: str, service: ScanService = Depends()):
    return await service.task(task_id)


@router.get(
    "/categories",
    response_model=list[ScanCategory],
    summary="Supported waste categories",
)
async def categories(service: ScanService = Depends()):
    return await service.categories()
