from fastapi import APIRouter, Depends, Path

from domains.my.schemas import UserProfile, UserUpdate
from domains.my.security import TokenPayload, access_token_dependency
from domains.my.services.my import MyService

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserProfile, summary="Get current user profile")
async def get_current_user(
    token: TokenPayload = Depends(access_token_dependency),
    service: MyService = Depends(MyService),
):
    return await service.get_current_user(auth_user_id=token.user_id)


@router.patch("/me", response_model=UserProfile, summary="Update current user profile")
async def update_current_user(
    payload: UserUpdate,
    token: TokenPayload = Depends(access_token_dependency),
    service: MyService = Depends(MyService),
):
    return await service.update_current_user(auth_user_id=token.user_id, payload=payload)


@router.delete("/me", summary="Delete current user")
async def delete_current_user(
    token: TokenPayload = Depends(access_token_dependency),
    service: MyService = Depends(MyService),
):
    await service.delete_current_user(auth_user_id=token.user_id)
    return {"message": "user deleted"}


@router.get("/{user_id}", response_model=UserProfile, summary="Get user profile")
async def get_user(user_id: int = Path(..., gt=0), service: MyService = Depends(MyService)):
    return await service.get_user(user_id)
