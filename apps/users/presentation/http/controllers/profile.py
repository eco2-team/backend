"""Profile controller - User profile endpoints."""

from __future__ import annotations

import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status

from apps.users.application.profile.commands import (
    DeleteUserInteractor,
    UpdateProfileInteractor,
)
from apps.users.application.profile.dto import UserUpdate
from apps.users.application.profile.exceptions import (
    InvalidPhoneNumberError,
    NoChangesProvidedError,
    UserNotFoundError,
)
from apps.users.application.profile.queries import GetProfileQuery
from apps.users.presentation.http.schemas import UserProfileResponse, UserUpdateRequest
from apps.users.setup.dependencies import (
    get_delete_user_interactor,
    get_get_profile_query,
    get_update_profile_interactor,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/me", tags=["profile"])


def get_user_id(
    x_user_id: Annotated[str | None, Header(alias="X-User-Id")] = None,
) -> UUID:
    """ext-authz에서 전달된 사용자 ID를 추출합니다."""
    if not x_user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing user ID",
        )
    try:
        return UUID(x_user_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user ID format",
        )


def get_provider(
    x_provider: Annotated[str | None, Header(alias="X-Provider")] = None,
) -> str:
    """ext-authz에서 전달된 OAuth 프로바이더를 추출합니다."""
    return x_provider or "unknown"


@router.get("", response_model=UserProfileResponse)
async def get_profile(
    user_id: UUID = Depends(get_user_id),
    provider: str = Depends(get_provider),
    query: GetProfileQuery = Depends(get_get_profile_query),
) -> UserProfileResponse:
    """현재 사용자 프로필을 조회합니다."""
    profile = await query.execute(user_id, provider)
    return UserProfileResponse(
        display_name=profile.display_name,
        nickname=profile.nickname,
        phone_number=profile.phone_number,
        provider=profile.provider,
        last_login_at=profile.last_login_at,
    )


@router.patch("", response_model=UserProfileResponse)
async def update_profile(
    request: UserUpdateRequest,
    user_id: UUID = Depends(get_user_id),
    provider: str = Depends(get_provider),
    interactor: UpdateProfileInteractor = Depends(get_update_profile_interactor),
) -> UserProfileResponse:
    """현재 사용자 프로필을 수정합니다."""
    try:
        update = UserUpdate(
            nickname=request.nickname,
            phone_number=request.phone_number,
        )
        profile = await interactor.execute(user_id, update, provider)
        return UserProfileResponse(
            display_name=profile.display_name,
            nickname=profile.nickname,
            phone_number=profile.phone_number,
            provider=profile.provider,
            last_login_at=profile.last_login_at,
        )
    except UserNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    except NoChangesProvidedError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No changes provided",
        )
    except InvalidPhoneNumberError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )


@router.delete("")
async def delete_user(
    user_id: UUID = Depends(get_user_id),
    interactor: DeleteUserInteractor = Depends(get_delete_user_interactor),
) -> Response:
    """현재 사용자 계정을 삭제합니다."""
    try:
        await interactor.execute(user_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except UserNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
