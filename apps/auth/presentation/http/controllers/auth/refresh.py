"""Refresh Controller.

토큰 갱신 엔드포인트입니다.
"""

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status

from apps.auth.application.token.commands import RefreshTokensInteractor
from apps.auth.application.token.dto import RefreshTokensRequest
from apps.auth.presentation.http.auth.cookie_params import (
    REFRESH_COOKIE_NAME,
    set_auth_cookies,
)
from apps.auth.presentation.http.schemas.auth import TokenResponse
from apps.auth.setup.dependencies import get_refresh_tokens_interactor

router = APIRouter()


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="토큰 갱신",
)
async def refresh(
    response: Response,
    refresh_token: str | None = Cookie(None, alias=REFRESH_COOKIE_NAME),
    interactor: RefreshTokensInteractor = Depends(get_refresh_tokens_interactor),
) -> TokenResponse:
    """토큰을 갱신합니다.

    리프레시 토큰으로 새 액세스/리프레시 토큰 쌍을 발급합니다.
    """
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token is required",
        )

    request = RefreshTokensRequest(refresh_token=refresh_token)
    result = await interactor.execute(request)

    # 새 쿠키 설정
    set_auth_cookies(
        response,
        access_token=result.access_token,
        refresh_token=result.refresh_token,
        access_expires_at=result.access_expires_at,
        refresh_expires_at=result.refresh_expires_at,
    )

    return TokenResponse(message="Token refreshed successfully")
