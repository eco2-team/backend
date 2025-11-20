from typing import Annotated, Optional

from fastapi import APIRouter, Cookie, Depends, Request, Response
from fastapi.responses import RedirectResponse

from domain.auth.api.v1.router import (
    access_token_dependency,
    auth_router,
    google_router,
    kakao_router,
    naver_router,
)
from domain.auth.core.config import get_settings
from domain.auth.schemas.auth import (
    AuthorizationResponse,
    AuthorizationSuccessResponse,
    LoginData,
    LoginSuccessResponse,
    LogoutData,
    LogoutSuccessResponse,
    OAuthAuthorizeParams,
    OAuthLoginRequest,
    User,
    UserSuccessResponse,
)
from domain.auth.services.auth import ACCESS_COOKIE_NAME, REFRESH_COOKIE_NAME, AuthService
from domain._shared.security import TokenPayload


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
    response: Response,
    service: Annotated[AuthService, Depends()],
):
    """Google OAuth 콜백을 처리하고 세션 쿠키를 설정합니다."""
    try:
        payload = OAuthLoginRequest(code=code, state=state)
        user = await service.login_with_provider(
            "google",
            payload,
            response=response,
            user_agent=request.headers.get("user-agent"),
            ip_address=request.client.host if request.client else None,
        )
        return LoginSuccessResponse(data=LoginData(user=user))
    except Exception:
        # OAuth 실패 시 프론트엔드 로그인 페이지로 리다이렉트
        settings = get_settings()
        return RedirectResponse(url=settings.oauth_failure_redirect_url)


@kakao_router.get(
    "/callback",
    summary="Kakao OAuth callback handler",
)
async def kakao_callback(
    code: str,
    state: str,
    request: Request,
    response: Response,
    service: Annotated[AuthService, Depends()],
):
    """Kakao OAuth 콜백을 처리하고 세션 쿠키를 설정합니다."""
    try:
        payload = OAuthLoginRequest(code=code, state=state)
        user = await service.login_with_provider(
            "kakao",
            payload,
            response=response,
            user_agent=request.headers.get("user-agent"),
            ip_address=request.client.host if request.client else None,
        )
        return LoginSuccessResponse(data=LoginData(user=user))
    except Exception:
        # OAuth 실패 시 프론트엔드 로그인 페이지로 리다이렉트
        settings = get_settings()
        return RedirectResponse(url=settings.oauth_failure_redirect_url)


@naver_router.get(
    "/callback",
    summary="Naver OAuth callback handler",
)
async def naver_callback(
    code: str,
    state: str,
    request: Request,
    response: Response,
    service: Annotated[AuthService, Depends()],
):
    """Naver OAuth 콜백을 처리하고 세션 쿠키를 설정합니다."""
    try:
        payload = OAuthLoginRequest(code=code, state=state)
        user = await service.login_with_provider(
            "naver",
            payload,
            response=response,
            user_agent=request.headers.get("user-agent"),
            ip_address=request.client.host if request.client else None,
        )
        return LoginSuccessResponse(data=LoginData(user=user))
    except Exception:
        # OAuth 실패 시 프론트엔드 로그인 페이지로 리다이렉트
        settings = get_settings()
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


@auth_router.post("/logout", response_model=LogoutSuccessResponse, summary="Invalidate current session")
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
