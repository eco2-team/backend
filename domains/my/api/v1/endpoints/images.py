from fastapi import APIRouter, Depends

from domains.my.schemas import ProfileImageUpdateRequest, UserProfile
from domains.my.security import TokenPayload, access_token_dependency
from domains.my.services.my import MyService

router = APIRouter(prefix="/images", tags=["images"])


@router.post(
    "/my",
    response_model=UserProfile,
    summary="Persist the CDN profile image URL for the current user",
)
async def save_profile_image(
    payload: ProfileImageUpdateRequest,
    token: TokenPayload = Depends(access_token_dependency),
    service: MyService = Depends(MyService),
):
    profile_image_url = payload.profile_image_url.strip() if payload.profile_image_url else None
    return await service.update_profile_image(
        auth_user_id=token.user_id,
        profile_image_url=profile_image_url,
    )
