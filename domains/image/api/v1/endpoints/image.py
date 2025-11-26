from fastapi import APIRouter, Depends, HTTPException, status

from domains.image.api.v1.dependencies import get_image_service
from domains.image.schemas.image import (
    ImageChannel,
    ImageUploadCallbackRequest,
    ImageUploadFinalizeResponse,
    ImageUploadRequest,
    ImageUploadResponse,
)
from domains.image.services.image import ImageService
from domains.image.services.image import (
    PendingUploadChannelMismatchError,
    PendingUploadNotFoundError,
)

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


@router.post(
    "/{channel}/callback",
    response_model=ImageUploadFinalizeResponse,
    summary="Confirm upload completion",
)
async def finalize_upload(
    channel: ImageChannel,
    payload: ImageUploadCallbackRequest,
    service: ImageService = Depends(get_image_service),
):
    try:
        return await service.finalize_upload(channel, payload)
    except PendingUploadNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Upload session not found or expired",
        ) from None
    except PendingUploadChannelMismatchError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Channel does not match the original upload request",
        ) from None
