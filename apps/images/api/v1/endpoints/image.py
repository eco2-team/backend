from fastapi import APIRouter, Depends, HTTPException, status

from images.api.v1.dependencies import get_image_service
from images.schemas.image import (
    ImageChannel,
    ImageUploadCallbackRequest,
    ImageUploadFinalizeResponse,
    ImageUploadRequest,
    ImageUploadResponse,
)
from images.services.image import ImageService
from images.services.image import (
    PendingUploadChannelMismatchError,
    PendingUploadNotFoundError,
    PendingUploadPermissionDeniedError,
)
from images.security import get_current_user, UserInfo

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
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Uploader mismatch",
        )
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
    try:
        return await service.finalize_upload(
            channel,
            payload,
            uploader_id=str(user.user_id),
        )
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
    except PendingUploadPermissionDeniedError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Uploader mismatch",
        ) from None
