from fastapi import APIRouter, Depends, Path, Query

from app.schemas.my import ActivityEntry, UserProfile, UserUpdate, UserPoints
from app.services.my import MyService

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/{user_id}", response_model=UserProfile, summary="Get user profile")
async def get_user(user_id: int = Path(..., gt=0), service: MyService = Depends()):
    return await service.get_user(user_id)


@router.patch("/{user_id}", response_model=UserProfile, summary="Update profile")
async def update_user(
    user_id: int,
    payload: UserUpdate,
    service: MyService = Depends(),
):
    return await service.update_user(user_id, payload)


@router.get("/{user_id}/points", response_model=UserPoints, summary="Retrieve points")
async def user_points(user_id: int, service: MyService = Depends()):
    return await service.user_points(user_id)


@router.get(
    "/{user_id}/history",
    response_model=list[ActivityEntry],
    summary="List user activity history",
)
async def history(
    user_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    service: MyService = Depends(),
):
    return await service.history(user_id, skip=skip, limit=limit)


@router.delete("/{user_id}", summary="Delete user")
async def delete_user(user_id: int, service: MyService = Depends()):
    await service.delete_user(user_id)
    return {"message": f"user {user_id} deleted"}
