"""Logout Controller.

로그아웃 엔드포인트입니다.
"""

from typing import Optional

from fastapi import APIRouter, Depends, Header, Response

from apps.auth.application.token.commands import LogoutInteractor
from apps.auth.application.token.dto import LogoutRequest
from apps.auth.presentation.http.auth.cookie_params import clear_auth_cookies
from apps.auth.presentation.http.schemas.auth import LogoutData, LogoutSuccessResponse
from apps.auth.setup.dependencies import get_logout_interactor

router = APIRouter()


def _parse_bearer(header_value: Optional[str]) -> Optional[str]:
    """Bearer 토큰에서 실제 토큰 값을 추출합니다."""
    if not header_value:
        return None
    scheme, _, token = header_value.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token.strip()


@router.post(
    "/logout",
    response_model=LogoutSuccessResponse,
    summary="로그아웃",
)
async def logout(
    response: Response,
    authorization: Optional[str] = Header(None, alias="Authorization"),
    refresh_authorization: Optional[str] = Header(None, alias="X-Refresh-Token"),
    interactor: LogoutInteractor = Depends(get_logout_interactor),
) -> LogoutSuccessResponse:
    """로그아웃을 처리합니다.

    EnvoyFilter가 쿠키를 헤더로 변환:
    - s_access -> Authorization: Bearer <token>
    - s_refresh -> X-Refresh-Token: Bearer <token>

    1. 토큰 블랙리스트 등록
    2. 쿠키 삭제
    """
    access_token = _parse_bearer(authorization)
    refresh_token = _parse_bearer(refresh_authorization)

    request = LogoutRequest(
        access_token=access_token,
        refresh_token=refresh_token,
    )

    await interactor.execute(request)

    # 쿠키 삭제
    clear_auth_cookies(response)

    return LogoutSuccessResponse(data=LogoutData())
