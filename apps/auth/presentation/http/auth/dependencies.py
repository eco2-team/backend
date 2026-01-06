"""Auth Dependencies.

FastAPI Depends용 인증 의존성입니다.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import Cookie, Depends, HTTPException, status

from apps.auth.application.token.queries.validate import (
    ValidatedUser,
    ValidateTokenQueryService,
)
from apps.auth.presentation.http.auth.cookie_params import ACCESS_COOKIE_NAME

if TYPE_CHECKING:
    pass


async def get_current_user(
    access_token: str | None = Cookie(None, alias=ACCESS_COOKIE_NAME),
    validate_token_service: ValidateTokenQueryService = Depends(),
) -> ValidatedUser:
    """현재 인증된 사용자 조회.

    Raises:
        HTTPException: 인증 실패
    """
    if not access_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    try:
        return await validate_token_service.execute(access_token)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
        ) from e


async def get_optional_user(
    access_token: str | None = Cookie(None, alias=ACCESS_COOKIE_NAME),
    validate_token_service: ValidateTokenQueryService = Depends(),
) -> ValidatedUser | None:
    """현재 사용자 조회 (선택적).

    인증되지 않은 경우 None 반환.
    """
    if not access_token:
        return None

    try:
        return await validate_token_service.execute(access_token)
    except Exception:
        return None
