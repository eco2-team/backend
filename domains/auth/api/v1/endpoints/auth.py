from typing import Annotated, Optional
import logging

from fastapi import Cookie, Depends, Request, Response
from fastapi.responses import RedirectResponse

from domains.auth.api.v1.routers import (
    access_token_dependency,
    auth_router,
    google_router,
    kakao_router,
    naver_router,
)
from domains.auth.core.config import get_settings
from domains.auth.schemas.auth import (
    AuthorizationSuccessResponse,
    LoginData,
    LoginSuccessResponse,
    LogoutData,
    LogoutSuccessResponse,
    OAuthAuthorizeParams,
    OAuthLoginRequest,
    UserSuccessResponse,
)
from domains.auth.services.auth import ACCESS_COOKIE_NAME, REFRESH_COOKIE_NAME, AuthService
from domains._shared.security import TokenPayload

logger = logging.getLogger(__name__)


@google_router.get(
    "",
    response_model=AuthorizationSuccessResponse,
    summary="Generate Google authorization URL",
)
async def authorize_google(
    params: Annotated[OAuthAuthorizeParams, Depends()],
    service: Annotated[AuthService, Depends()],
):
    result = await service.authorize("google", params)
    return AuthorizationSuccessResponse(data=result)


@kakao_router.get(
    "",
    response_model=AuthorizationSuccessResponse,
    summary="Generate Kakao authorization URL",
)
async def authorize_kakao(
    params: Annotated[OAuthAuthorizeParams, Depends()],
    service: Annotated[AuthService, Depends()],
):
    result = await service.authorize("kakao", params)
    return AuthorizationSuccessResponse(data=result)


@naver_router.get(
    "",
    response_model=AuthorizationSuccessResponse,
    summary="Generate Naver authorization URL",
)
async def authorize_naver(
    params: Annotated[OAuthAuthorizeParams, Depends()],
    service: Annotated[AuthService, Depends()],
):
    result = await service.authorize("naver", params)
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
    success_response = RedirectResponse(url=settings.frontend_url)
    try:
        payload = OAuthLoginRequest(code=code, state=state)
        await service.login_with_provider(
            "google",
            payload,
            response=success_response,
            user_agent=request.headers.get("user-agent"),
            ip_address=request.client.host if request.client else None,
        )
        # 성공 시 프론트엔드 홈으로 리다이렉트
        return success_response
    except Exception as e:
        # OAuth 실패 시 프론트엔드 로그인 페이지로 리다이렉트
        logger.error(f"Google OAuth callback failed: {type(e).__name__}: {str(e)}", exc_info=True)
        return RedirectResponse(url=settings.oauth_failure_redirect_url)


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
    success_response = RedirectResponse(url=settings.frontend_url)
    try:
        payload = OAuthLoginRequest(code=code, state=state)
        await service.login_with_provider(
            "kakao",
            payload,
            response=success_response,
            user_agent=request.headers.get("user-agent"),
            ip_address=request.client.host if request.client else None,
        )
        # 성공 시 프론트엔드 홈으로 리다이렉트
        return success_response
    except Exception as e:
        # OAuth 실패 시 프론트엔드 로그인 페이지로 리다이렉트
        logger.error(f"Kakao OAuth callback failed: {type(e).__name__}: {str(e)}", exc_info=True)
        return RedirectResponse(url=settings.oauth_failure_redirect_url)


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
    success_response = RedirectResponse(url=settings.frontend_url)
    try:
        payload = OAuthLoginRequest(code=code, state=state)
        await service.login_with_provider(
            "naver",
            payload,
            response=success_response,
            user_agent=request.headers.get("user-agent"),
            ip_address=request.client.host if request.client else None,
        )
        # 성공 시 프론트엔드 홈으로 리다이렉트
        return success_response
    except Exception as e:
        # OAuth 실패 시 프론트엔드 로그인 페이지로 리다이렉트
        logger.error(f"Naver OAuth callback failed: {type(e).__name__}: {str(e)}", exc_info=True)
        return RedirectResponse(url=settings.oauth_failure_redirect_url)


@auth_router.post(
    "/login/{provider}",
    response_model=LoginSuccessResponse,
    summary="Exchange OAuth code for session cookies",
)
async def login_with_provider(
    provider: str,
    payload: OAuthLoginRequest,
    request: Request,
    response: Response,
    service: Annotated[AuthService, Depends()],
):
    user = await service.login_with_provider(
        provider,
        payload,
        response=response,
        user_agent=request.headers.get("user-agent"),
        ip_address=request.client.host if request.client else None,
    )
    return LoginSuccessResponse(data=LoginData(user=user))


@auth_router.post(
    "/refresh",
    response_model=LoginSuccessResponse,
    summary="Rotate session cookies",
)
async def refresh_session(
    response: Response,
    service: Annotated[AuthService, Depends()],
    refresh_token: Annotated[Optional[str], Cookie(alias=REFRESH_COOKIE_NAME)] = None,
):
    user = await service.refresh_session(refresh_token, response=response)
    return LoginSuccessResponse(data=LoginData(user=user))


@auth_router.post(
    "/logout", response_model=LogoutSuccessResponse, summary="Invalidate current session"
)
async def logout(
    response: Response,
    service: Annotated[AuthService, Depends()],
    access_token: Annotated[Optional[str], Cookie(alias=ACCESS_COOKIE_NAME)] = None,
    refresh_token: Annotated[Optional[str], Cookie(alias=REFRESH_COOKIE_NAME)] = None,
):
    await service.logout(access_token=access_token, refresh_token=refresh_token, response=response)
    return LogoutSuccessResponse(data=LogoutData())


@auth_router.get("/me", response_model=UserSuccessResponse, summary="Fetch current user profile")
async def get_current_user(
    payload: Annotated[TokenPayload, Depends(access_token_dependency)],
    service: Annotated[AuthService, Depends()],
):
    user = await service.get_current_user(payload)
    return UserSuccessResponse(data=user)
