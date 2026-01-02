"""Authorize Controller.

OAuth 인증 URL 생성 엔드포인트입니다.
"""

from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Optional

from fastapi import APIRouter, Depends, Header, Query, Request

from apps.auth.application.oauth.commands import OAuthAuthorizeInteractor
from apps.auth.application.oauth.dto import OAuthAuthorizeRequest
from apps.auth.presentation.http.schemas.auth import (
    AuthorizationData,
    AuthorizationSuccessResponse,
    AuthorizeResponse,
)
from apps.auth.presentation.http.utils.redirect import FRONTEND_ORIGIN_HEADER
from apps.auth.setup.dependencies import get_oauth_authorize_interactor

router = APIRouter()

# OAuth state TTL (레거시 호환)
OAUTH_STATE_TTL_SECONDS = 600  # 10분


class OAuthProviderPath(str, Enum):
    """지원하는 OAuth 프로바이더 (path parameter용)."""

    google = "google"
    kakao = "kakao"
    naver = "naver"


@router.get(
    "/{provider}/authorize",
    response_model=AuthorizeResponse,
    summary="OAuth 인증 URL 생성",
)
async def authorize(
    provider: OAuthProviderPath,
    request: Request,
    redirect_uri: str | None = Query(None, description="콜백 리다이렉트 URI"),
    state: str | None = Query(None, description="커스텀 상태 값"),
    device_id: str | None = Query(None, description="기기 ID"),
    frontend_origin: str | None = Query(None, description="프론트엔드 오리진 (쿼리)"),
    x_frontend_origin: Optional[str] = Header(
        None,
        alias=FRONTEND_ORIGIN_HEADER,
        description="프론트엔드 오리진 (헤더, 멀티 프론트엔드 지원)",
    ),
    interactor: OAuthAuthorizeInteractor = Depends(get_oauth_authorize_interactor),
) -> AuthorizeResponse:
    """OAuth 인증 URL을 생성합니다.

    클라이언트는 반환된 authorization_url로 리다이렉트해야 합니다.

    프론트엔드 오리진은 쿼리 파라미터 또는 X-Frontend-Origin 헤더로 전달할 수 있습니다.
    이 값은 state에 저장되어 콜백 시 프론트엔드로 리다이렉트하는 데 사용됩니다.
    """
    # 프론트엔드 오리진: 쿼리 > 헤더
    resolved_frontend_origin = frontend_origin or x_frontend_origin

    auth_request = OAuthAuthorizeRequest(
        provider=provider,
        redirect_uri=redirect_uri,
        state=state,
        device_id=device_id,
        frontend_origin=resolved_frontend_origin,
    )
    result = await interactor.execute(auth_request)

    return AuthorizeResponse(
        authorization_url=result.authorization_url,
        state=result.state,
    )


async def _build_authorization_response(
    provider: str,
    redirect_uri: str | None,
    device_id: str | None,
    frontend_origin: str | None,
    interactor: OAuthAuthorizeInteractor,
) -> AuthorizationSuccessResponse:
    """OAuth 인증 URL 생성 공통 로직."""
    auth_request = OAuthAuthorizeRequest(
        provider=provider,
        redirect_uri=redirect_uri,
        device_id=device_id,
        frontend_origin=frontend_origin,
    )
    result = await interactor.execute(auth_request)

    # 레거시 응답 형식 (expires_at 포함)
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=OAUTH_STATE_TTL_SECONDS)
    return AuthorizationSuccessResponse(
        data=AuthorizationData(
            provider=provider,
            state=result.state,
            authorization_url=result.authorization_url,
            expires_at=expires_at,
        )
    )


@router.get(
    "/{provider}",
    response_model=AuthorizationSuccessResponse,
    summary="OAuth 인증 URL 생성",
    description="JSON 응답으로 authorization_url 반환. 프론트엔드가 직접 이동해야 함.",
)
async def authorize_provider(
    provider: OAuthProviderPath,
    request: Request,
    redirect_uri: str | None = Query(None),
    device_id: str | None = Query(None),
    frontend_origin: str | None = Query(None),
    x_frontend_origin: Optional[str] = Header(None, alias=FRONTEND_ORIGIN_HEADER),
    interactor: OAuthAuthorizeInteractor = Depends(get_oauth_authorize_interactor),
) -> AuthorizationSuccessResponse:
    """OAuth 인증 URL을 JSON으로 반환합니다.

    프론트엔드는 응답의 authorization_url로 직접 이동해야 합니다.
    """
    resolved_frontend_origin = frontend_origin or x_frontend_origin
    return await _build_authorization_response(
        provider, redirect_uri, device_id, resolved_frontend_origin, interactor
    )


@router.get(
    "/{provider}/login",
    response_model=AuthorizationSuccessResponse,
    summary="OAuth 로그인 URL 생성",
    description="/{provider}와 동일. JSON 응답으로 authorization_url 반환.",
)
async def login_provider(
    provider: OAuthProviderPath,
    request: Request,
    redirect_uri: str | None = Query(None),
    device_id: str | None = Query(None),
    frontend_origin: str | None = Query(None, description="프론트엔드 오리진 (쿼리)"),
    x_frontend_origin: Optional[str] = Header(
        None,
        alias=FRONTEND_ORIGIN_HEADER,
        description="프론트엔드 오리진 (헤더)",
    ),
    interactor: OAuthAuthorizeInteractor = Depends(get_oauth_authorize_interactor),
) -> AuthorizationSuccessResponse:
    """OAuth 인증 URL을 JSON으로 반환합니다.

    /{provider}와 동일하게 동작합니다.
    프론트엔드는 응답의 authorization_url로 직접 이동해야 합니다.
    """
    resolved_frontend_origin = frontend_origin or x_frontend_origin
    return await _build_authorization_response(
        provider, redirect_uri, device_id, resolved_frontend_origin, interactor
    )
