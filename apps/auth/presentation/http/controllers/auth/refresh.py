"""Refresh Controller.

토큰 갱신 엔드포인트입니다.
"""

from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status

from apps.auth.application.token.commands import RefreshTokensInteractor
from apps.auth.application.token.dto import RefreshTokensRequest
from apps.auth.presentation.http.auth.cookie_params import set_auth_cookies
from apps.auth.setup.dependencies import get_refresh_tokens_interactor

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
    "/refresh",
    summary="토큰 갱신",
    status_code=status.HTTP_201_CREATED,
)
async def refresh(
    response: Response,
    authorization: Optional[str] = Header(None, alias="Authorization"),
    refresh_authorization: Optional[str] = Header(None, alias="X-Refresh-Token"),
    interactor: RefreshTokensInteractor = Depends(get_refresh_tokens_interactor),
) -> None:
    """토큰을 갱신합니다.

    EnvoyFilter가 쿠키를 헤더로 변환:
    - s_refresh -> X-Refresh-Token: Bearer <token> 또는 Authorization: Bearer <token>

    리프레시 토큰으로 새 액세스/리프레시 토큰 쌍을 발급합니다.
    """
    # X-Refresh-Token 우선, 없으면 Authorization에서 추출
    refresh_token = _parse_bearer(refresh_authorization) or _parse_bearer(authorization)

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

    response.status_code = status.HTTP_201_CREATED
    return None
