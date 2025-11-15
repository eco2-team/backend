from fastapi import APIRouter, Depends

from app.services.info import InfoService

router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get("/", summary="Info service metrics")
async def metrics(service: InfoService = Depends()):
    return await service.metrics()
