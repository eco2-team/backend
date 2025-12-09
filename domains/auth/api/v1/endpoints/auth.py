from typing import Annotated, Optional
import logging
from urllib.parse import urlparse, urlunparse

from fastapi import Depends, Request, Response, Header, status
from fastapi.responses import RedirectResponse

from domains.auth.api.v1.routers import (
    auth_router,
    google_router,
    kakao_router,
    naver_router,
)
from domains.auth.core.config import get_settings
from domains.auth.schemas.auth import (
    AuthorizationSuccessResponse,
    LogoutData,
    LogoutSuccessResponse,
    OAuthAuthorizeParams,
    OAuthLoginRequest,
)
from domains.auth.services.auth import AuthService
from domains.auth.services.key_manager import KeyManager

logger = logging.getLogger(__name__)


@auth_router.get("/.well-known/jwks.json", summary="Get JWKS for token verification")
async def get_jwks():
    return KeyManager.get_jwks()


def _is_default_port(scheme: str, port: str) -> bool:
    scheme = (scheme or "").lower()
    return (scheme == "https" and port == "443") or (scheme == "http" and port == "80")


def _get_request_origin(request: Request) -> Optional[str]:
    headers = request.headers
    forwarded_host = headers.get("x-forwarded-host")
    forwarded_proto = headers.get("x-forwarded-proto")
    forwarded_port = headers.get("x-forwarded-port")

    host_header = forwarded_host or headers.get("host")
    host = host_header.split(",")[0].strip() if host_header else request.url.hostname
    if not host:
        return None

    scheme = (
        forwarded_proto.split(",")[0].strip()
        if forwarded_proto
        else (request.url.scheme or "https")
    )

    if ":" not in host:
        if forwarded_port:
            port = forwarded_port.split(",")[0].strip()
        else:
            port = str(request.url.port) if request.url.port else None
        if port and not _is_default_port(scheme, port):
            host = f"{host}:{port}"

    return f"{scheme}://{host}"


FRONTEND_ORIGIN_HEADER = "x-frontend-origin"


def _build_frontend_success_url(frontend_url: str) -> str:
    sanitized = frontend_url.rstrip("/")
    return f"{sanitized}/#/home"


def _build_frontend_redirect_url(
    request: Request, fallback_url: str, frontend_origin: str | None
) -> str:
    origin = frontend_origin or _get_request_origin(request)
    if not origin:
        return fallback_url

    parsed_origin = urlparse(origin)
    parsed_fallback = urlparse(fallback_url)

    scheme = parsed_origin.scheme or parsed_fallback.scheme
    netloc = parsed_origin.netloc or parsed_fallback.netloc
    if not scheme or not netloc:
        return fallback_url

    path = parsed_fallback.path or "/"

    return urlunparse(
        (
            scheme,
            netloc,
            path,
            parsed_fallback.params,
            parsed_fallback.query,
            parsed_fallback.fragment,
        )
    )


def _build_frontend_redirect_response(
    request: Request, fallback_url: str, frontend_origin: str | None
) -> RedirectResponse:
    redirect_url = _build_frontend_redirect_url(request, fallback_url, frontend_origin)
    return RedirectResponse(url=redirect_url)


@google_router.get(
    "",
    response_model=AuthorizationSuccessResponse,
    summary="Generate Google authorization URL",
)
async def authorize_google(
    params: Annotated[OAuthAuthorizeParams, Depends()],
    service: Annotated[AuthService, Depends()],
    request: Request,
):
    frontend_origin = params.frontend_origin or request.headers.get(FRONTEND_ORIGIN_HEADER)
    result = await service.authorize(
        "google", params.model_copy(update={"frontend_origin": frontend_origin})
    )
    return AuthorizationSuccessResponse(data=result)


@kakao_router.get(
    "",
    response_model=AuthorizationSuccessResponse,
    summary="Generate Kakao authorization URL",
)
async def authorize_kakao(
    params: Annotated[OAuthAuthorizeParams, Depends()],
    service: Annotated[AuthService, Depends()],
    request: Request,
):
    frontend_origin = params.frontend_origin or request.headers.get(FRONTEND_ORIGIN_HEADER)
    result = await service.authorize(
        "kakao", params.model_copy(update={"frontend_origin": frontend_origin})
    )
    return AuthorizationSuccessResponse(data=result)


@naver_router.get(
    "",
    response_model=AuthorizationSuccessResponse,
    summary="Generate Naver authorization URL",
)
async def authorize_naver(
    params: Annotated[OAuthAuthorizeParams, Depends()],
    service: Annotated[AuthService, Depends()],
    request: Request,
):
    frontend_origin = params.frontend_origin or request.headers.get(FRONTEND_ORIGIN_HEADER)
    result = await service.authorize(
        "naver", params.model_copy(update={"frontend_origin": frontend_origin})
    )
    return AuthorizationSuccessResponse(data=result)


# OAuth Callback Endpoints
@google_router.get(
    "/callback",
    summary="Google OAuth callback handler",
)
async def google_callback(
    code: str,
    state: str,
    request: Request,
    service: Annotated[AuthService, Depends()],
):
    """Google OAuth 콜백을 처리하고 세션 쿠키를 설정합니다."""
    settings = get_settings()
    frontend_origin = request.headers.get(FRONTEND_ORIGIN_HEADER)
    success_url = _build_frontend_success_url(settings.frontend_url)
    success_response = RedirectResponse(url=success_url)
    try:
        payload = OAuthLoginRequest(code=code, state=state)
        await service.login_with_provider(
            "google",
            payload,
            response=success_response,
            user_agent=request.headers.get("user-agent"),
            ip_address=request.client.host if request.client else None,
        )
        redirect_origin = frontend_origin or service.get_state_frontend_origin()
        redirect_url = _build_frontend_redirect_url(request, success_url, redirect_origin)
        success_response.headers["location"] = redirect_url
        # 성공 시 프론트엔드 홈으로 리다이렉트
        return success_response
    except Exception as e:
        # OAuth 실패 시 프론트엔드 로그인 페이지로 리다이렉트
        logger.error(f"Google OAuth callback failed: {type(e).__name__}: {str(e)}", exc_info=True)
        return _build_frontend_redirect_response(
            request,
            settings.oauth_failure_redirect_url,
            frontend_origin or service.get_state_frontend_origin(),
        )


@kakao_router.get(
    "/callback",
    summary="Kakao OAuth callback handler",
)
async def kakao_callback(
    code: str,
    state: str,
    request: Request,
    service: Annotated[AuthService, Depends()],
):
    """Kakao OAuth 콜백을 처리하고 세션 쿠키를 설정합니다."""
    settings = get_settings()
    frontend_origin = request.headers.get(FRONTEND_ORIGIN_HEADER)
    success_url = _build_frontend_success_url(settings.frontend_url)
    success_response = RedirectResponse(url=success_url)
    try:
        payload = OAuthLoginRequest(code=code, state=state)
        await service.login_with_provider(
            "kakao",
            payload,
            response=success_response,
            user_agent=request.headers.get("user-agent"),
            ip_address=request.client.host if request.client else None,
        )
        redirect_origin = frontend_origin or service.get_state_frontend_origin()
        redirect_url = _build_frontend_redirect_url(request, success_url, redirect_origin)
        success_response.headers["location"] = redirect_url
        # 성공 시 프론트엔드 홈으로 리다이렉트
        return success_response
    except Exception as e:
        # OAuth 실패 시 프론트엔드 로그인 페이지로 리다이렉트
        logger.error(f"Kakao OAuth callback failed: {type(e).__name__}: {str(e)}", exc_info=True)
        return _build_frontend_redirect_response(
            request,
            settings.oauth_failure_redirect_url,
            frontend_origin or service.get_state_frontend_origin(),
        )


@naver_router.get(
    "/callback",
    summary="Naver OAuth callback handler",
)
async def naver_callback(
    code: str,
    state: str,
    request: Request,
    service: Annotated[AuthService, Depends()],
):
    """Naver OAuth 콜백을 처리하고 세션 쿠키를 설정합니다."""
    settings = get_settings()
    frontend_origin = request.headers.get(FRONTEND_ORIGIN_HEADER)
    success_url = _build_frontend_success_url(settings.frontend_url)
    success_response = RedirectResponse(url=success_url)
    try:
        payload = OAuthLoginRequest(code=code, state=state)
        await service.login_with_provider(
            "naver",
            payload,
            response=success_response,
            user_agent=request.headers.get("user-agent"),
            ip_address=request.client.host if request.client else None,
        )
        redirect_origin = frontend_origin or service.get_state_frontend_origin()
        redirect_url = _build_frontend_redirect_url(request, success_url, redirect_origin)
        success_response.headers["location"] = redirect_url
        # 성공 시 프론트엔드 홈으로 리다이렉트
        return success_response
    except Exception as e:
        # OAuth 실패 시 프론트엔드 로그인 페이지로 리다이렉트
        logger.error(f"Naver OAuth callback failed: {type(e).__name__}: {str(e)}", exc_info=True)
        return _build_frontend_redirect_response(
            request,
            settings.oauth_failure_redirect_url,
            frontend_origin or service.get_state_frontend_origin(),
        )


def _parse_bearer(header_value: Optional[str]) -> Optional[str]:
    if not header_value:
        return None
    scheme, _, token = header_value.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token.strip()


@auth_router.post(
    "/refresh",
    summary="Rotate session tokens (header-based)",
    status_code=status.HTTP_201_CREATED,
)
async def refresh_session(
    response: Response,
    service: Annotated[AuthService, Depends()],
    authorization: Annotated[Optional[str], Header(alias="Authorization")] = None,
    refresh_authorization: Annotated[Optional[str], Header(alias="X-Refresh-Token")] = None,
):
    # EnvoyFilter가 refresh 쿠키를 헤더로 변환했다는 가정 하에 Authorization 또는 X-Refresh-Token에서 추출
    refresh_token = _parse_bearer(refresh_authorization) or _parse_bearer(authorization)
    await service.refresh_session(refresh_token, response=response)
    response.status_code = status.HTTP_201_CREATED
    return None


@auth_router.post(
    "/logout", response_model=LogoutSuccessResponse, summary="Invalidate current session"
)
async def logout(
    response: Response,
    service: Annotated[AuthService, Depends()],
    authorization: Annotated[Optional[str], Header(alias="Authorization")] = None,
    refresh_authorization: Annotated[Optional[str], Header(alias="X-Refresh-Token")] = None,
):
    access_token = _parse_bearer(authorization)
    refresh_token = _parse_bearer(refresh_authorization)
    await service.logout(access_token=access_token, refresh_token=refresh_token, response=response)
    return LogoutSuccessResponse(data=LogoutData())
