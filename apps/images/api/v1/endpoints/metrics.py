from fastapi import APIRouter, Depends

from images.api.v1.dependencies import get_image_service
from images.services.image import ImageService

router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get("/", summary="Image service metrics")
async def metrics(service: ImageService = Depends(get_image_service)):
    return await service.metrics()
