"""Logout Controller.

로그아웃 엔드포인트입니다.
"""

from fastapi import APIRouter, Cookie, Depends, Response

from apps.auth.application.token.commands import LogoutInteractor
from apps.auth.application.token.dto import LogoutRequest
from apps.auth.presentation.http.auth.cookie_params import (
    ACCESS_COOKIE_NAME,
    REFRESH_COOKIE_NAME,
    clear_auth_cookies,
)
from apps.auth.presentation.http.schemas.auth import TokenResponse
from apps.auth.setup.dependencies import get_logout_interactor

router = APIRouter()


@router.post(
    "/logout",
    response_model=TokenResponse,
    summary="로그아웃",
)
async def logout(
    response: Response,
    access_token: str | None = Cookie(None, alias=ACCESS_COOKIE_NAME),
    refresh_token: str | None = Cookie(None, alias=REFRESH_COOKIE_NAME),
    interactor: LogoutInteractor = Depends(get_logout_interactor),
) -> TokenResponse:
    """로그아웃을 처리합니다.

    1. 토큰 블랙리스트 등록
    2. 쿠키 삭제
    """
    request = LogoutRequest(
        access_token=access_token,
        refresh_token=refresh_token,
    )

    await interactor.execute(request)

    # 쿠키 삭제
    clear_auth_cookies(response)

    return TokenResponse(message="Logged out successfully")
