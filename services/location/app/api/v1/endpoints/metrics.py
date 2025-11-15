from fastapi import APIRouter, Depends

from app.services.location import LocationService

router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get("/", summary="Location service metrics")
async def metrics(service: LocationService = Depends()):
    return await service.metrics()
