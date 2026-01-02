"""Callback Controller.

OAuth 콜백 처리 엔드포인트입니다.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from fastapi.responses import RedirectResponse

from apps.auth.application.oauth.commands import OAuthCallbackInteractor
from apps.auth.application.oauth.dto import OAuthCallbackRequest
from apps.auth.presentation.http.schemas.auth import UserResponse
from apps.auth.presentation.http.auth.cookie_params import set_auth_cookies
from apps.auth.presentation.http.utils.redirect import (
    FRONTEND_ORIGIN_HEADER,
    build_frontend_redirect_url,
    build_frontend_success_url,
    build_frontend_redirect_response,
)
from apps.auth.setup.config import get_settings
from apps.auth.setup.dependencies import get_oauth_callback_interactor

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "/{provider}/callback",
    response_model=UserResponse,
    summary="OAuth 콜백 처리",
)
async def callback(
    provider: str,
    request: Request,
    response: Response,
    code: str = Query(..., description="OAuth 인증 코드"),
    state: str = Query(..., description="상태 값"),
    redirect_uri: str | None = Query(None, description="리다이렉트 URI"),
    x_frontend_origin: Optional[str] = Header(
        None,
        alias=FRONTEND_ORIGIN_HEADER,
        description="프론트엔드 오리진 (멀티 프론트엔드 지원)",
    ),
    interactor: OAuthCallbackInteractor = Depends(get_oauth_callback_interactor),
) -> UserResponse | RedirectResponse:
    """OAuth 콜백을 처리합니다.

    1. 인증 코드로 토큰 교환
    2. 사용자 프로필 조회
    3. 사용자 생성 또는 조회
    4. JWT 토큰 발급 및 쿠키 설정
    5. 프론트엔드로 리다이렉트

    X-Frontend-Origin 헤더로 동적 프론트엔드 리다이렉트를 지원합니다.
    """
    settings = get_settings()

    # 프론트엔드 오리진 결정 (헤더 > state에서 복원 > 기본값)
    frontend_origin = x_frontend_origin

    try:
        callback_request = OAuthCallbackRequest(
            provider=provider,
            code=code,
            state=state,
            redirect_uri=redirect_uri,
            user_agent=request.headers.get("user-agent"),
            ip_address=request.client.host if request.client else None,
            frontend_origin=frontend_origin,
        )

        result = await interactor.execute(callback_request)

        # 프론트엔드 리다이렉트 URL 결정
        # 우선순위: state에서 복원된 오리진 > 헤더 > 기본값
        redirect_origin = result.frontend_origin or frontend_origin
        success_url = build_frontend_success_url(settings.frontend_url)
        redirect_url = build_frontend_redirect_url(request, success_url, redirect_origin)

        # RedirectResponse 생성
        redirect_response = RedirectResponse(url=redirect_url, status_code=302)

        # 쿠키 설정 (RedirectResponse에 직접 설정)
        set_auth_cookies(
            redirect_response,
            access_token=result.access_token,
            refresh_token=result.refresh_token,
            access_expires_at=result.access_expires_at,
            refresh_expires_at=result.refresh_expires_at,
        )

        logger.info(
            f"OAuth callback success: provider={provider}, "
            f"user_id={result.user_id}, redirect={redirect_url}"
        )

        # 프론트엔드로 리다이렉트 (쿠키 포함)
        return redirect_response

    except Exception as e:
        # OAuth 실패 시 프론트엔드 로그인 페이지로 리다이렉트
        logger.error(
            f"{provider.capitalize()} OAuth callback failed: " f"{type(e).__name__}: {str(e)}",
            exc_info=True,
        )
        return build_frontend_redirect_response(
            request,
            settings.oauth_failure_redirect_url,
            frontend_origin,
        )
