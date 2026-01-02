"""Authorize Controller.

OAuth 인증 URL 생성 엔드포인트입니다.
"""

from typing import Optional

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import RedirectResponse

from apps.auth.application.oauth.commands import OAuthAuthorizeInteractor
from apps.auth.application.oauth.dto import OAuthAuthorizeRequest
from apps.auth.presentation.http.schemas.auth import AuthorizeResponse
from apps.auth.presentation.http.utils.redirect import FRONTEND_ORIGIN_HEADER
from apps.auth.setup.dependencies import get_oauth_authorize_interactor

router = APIRouter()


@router.get(
    "/{provider}/authorize",
    response_model=AuthorizeResponse,
    summary="OAuth 인증 URL 생성",
)
async def authorize(
    provider: str,
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


async def _do_login_redirect(
    provider: str,
    redirect_uri: str | None,
    device_id: str | None,
    frontend_origin: str | None,
    interactor: OAuthAuthorizeInteractor,
) -> RedirectResponse:
    """OAuth 로그인 공통 로직."""
    auth_request = OAuthAuthorizeRequest(
        provider=provider,
        redirect_uri=redirect_uri,
        device_id=device_id,
        frontend_origin=frontend_origin,
    )
    result = await interactor.execute(auth_request)
    return RedirectResponse(url=result.authorization_url)


@router.get(
    "/{provider}",
    response_class=RedirectResponse,
    summary="OAuth 로그인 (레거시)",
    deprecated=True,
    description="Deprecated: /{provider}/login 사용 권장",
)
async def login_legacy(
    provider: str,
    request: Request,
    redirect_uri: str | None = Query(None),
    device_id: str | None = Query(None),
    frontend_origin: str | None = Query(None),
    x_frontend_origin: Optional[str] = Header(None, alias=FRONTEND_ORIGIN_HEADER),
    interactor: OAuthAuthorizeInteractor = Depends(get_oauth_authorize_interactor),
) -> RedirectResponse:
    """[레거시] OAuth 인증 페이지로 리다이렉트합니다.

    하위 호환성을 위해 유지됩니다. /{provider}/login 사용을 권장합니다.
    """
    resolved_frontend_origin = frontend_origin or x_frontend_origin
    return await _do_login_redirect(
        provider, redirect_uri, device_id, resolved_frontend_origin, interactor
    )


@router.get(
    "/{provider}/login",
    response_class=RedirectResponse,
    summary="OAuth 로그인 (리다이렉트)",
)
async def login_redirect(
    provider: str,
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
) -> RedirectResponse:
    """OAuth 인증 페이지로 직접 리다이렉트합니다.

    프론트엔드 오리진은 쿼리 파라미터 또는 X-Frontend-Origin 헤더로 전달할 수 있습니다.
    """
    resolved_frontend_origin = frontend_origin or x_frontend_origin
    return await _do_login_redirect(
        provider, redirect_uri, device_id, resolved_frontend_origin, interactor
    )
