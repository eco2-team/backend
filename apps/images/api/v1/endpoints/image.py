from fastapi import APIRouter, Depends

from images.api.v1.dependencies import get_image_service
from images.core.exceptions.upload import UploaderMismatchError
from images.schemas.image import (
    ImageChannel,
    ImageUploadCallbackRequest,
    ImageUploadFinalizeResponse,
    ImageUploadRequest,
    ImageUploadResponse,
)
from images.security import UserInfo, get_current_user
from images.services.image import ImageService

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
    user: UserInfo = Depends(get_current_user),
):
    user_id = str(user.user_id)
    if payload.uploader_id and payload.uploader_id != user_id:
        raise UploaderMismatchError()
    return await service.create_upload_url(
        channel,
        payload,
        uploader_id=user_id,
    )


@router.post(
    "/{channel}/callback",
    response_model=ImageUploadFinalizeResponse,
    summary="Confirm upload completion",
)
async def finalize_upload(
    channel: ImageChannel,
    payload: ImageUploadCallbackRequest,
    service: ImageService = Depends(get_image_service),
    user: UserInfo = Depends(get_current_user),
):
    return await service.finalize_upload(
        channel,
        payload,
        uploader_id=str(user.user_id),
    )
