from fastapi import APIRouter, Depends

from app.services.my import MyService

router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get("/", summary="My service metrics")
async def metrics(service: MyService = Depends()):
    return await service.metrics()
