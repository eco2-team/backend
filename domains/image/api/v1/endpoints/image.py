from fastapi import APIRouter, Depends

from domains.image.api.v1.dependencies import get_image_service
from domains.image.schemas.image import (
    ImageChannel,
    ImageUploadRequest,
    ImageUploadResponse,
)
from domains.image.services.image import ImageService

router = APIRouter(prefix="/images", tags=["images"])


@router.post(
    "/{channel}",
    response_model=ImageUploadResponse,
    summary="Create presigned upload URL",
)
async def create_upload_url(
    channel: ImageChannel,
    payload: ImageUploadRequest,
    service: ImageService = Depends(get_image_service),
):
    return await service.create_upload_url(channel, payload)
