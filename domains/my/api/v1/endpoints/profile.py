from fastapi import APIRouter, Depends

from domains.my.schemas import UserProfile, UserUpdate
from domains.my.security import get_current_user, UserInfo
from domains.my.services.my import MyService

router = APIRouter(prefix="/user", tags=["user"])


@router.get("/me", response_model=UserProfile, summary="Get current user profile")
async def get_me(
    user: UserInfo = Depends(get_current_user),
    service: MyService = Depends(MyService),
):
    return await service.get_current_user(auth_user_id=user.user_id, provider=user.provider)


@router.patch("/me", response_model=UserProfile, summary="Update current user profile")
async def update_me(
    payload: UserUpdate,
    user: UserInfo = Depends(get_current_user),
    service: MyService = Depends(MyService),
):
    return await service.update_current_user(
        auth_user_id=user.user_id,
        payload=payload,
        provider=user.provider,
    )


@router.delete("/me", summary="Delete current user")
async def delete_me(
    user: UserInfo = Depends(get_current_user),
    service: MyService = Depends(MyService),
):
    await service.delete_current_user(auth_user_id=user.user_id)
    return {"message": "user deleted"}
