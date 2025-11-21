from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import RedirectResponse

from app.core.config import get_settings
from app.schemas.auth import User
from app.schemas.oauth import OAuthAuthorizeParams, OAuthAuthorizeResponse, OAuthLoginRequest
from app.services.oauth import OAuthService

# OAuth provider routers
google_router = APIRouter(prefix="/auth/google", tags=["auth/google"])
kakao_router = APIRouter(prefix="/auth/kakao", tags=["auth/kakao"])
naver_router = APIRouter(prefix="/auth/naver", tags=["auth/naver"])


@google_router.get(
    "",
    response_model=OAuthAuthorizeResponse,
    summary="Generate Google authorization URL",
)
async def authorize_google(
    params: Annotated[OAuthAuthorizeParams, Depends()],
    service: Annotated[OAuthService, Depends()],
):
    """Google OAuth 인증 URL을 생성합니다."""
    result = await service.authorize("google", params)
    return {"success": True, "data": result}


@kakao_router.get(
    "",
    response_model=OAuthAuthorizeResponse,
    summary="Generate Kakao authorization URL",
)
async def authorize_kakao(
    params: Annotated[OAuthAuthorizeParams, Depends()],
    service: Annotated[OAuthService, Depends()],
):
    """Kakao OAuth 인증 URL을 생성합니다."""
    result = await service.authorize("kakao", params)
    return {"success": True, "data": result}


@naver_router.get(
    "",
    response_model=OAuthAuthorizeResponse,
    summary="Generate Naver authorization URL",
)
async def authorize_naver(
    params: Annotated[OAuthAuthorizeParams, Depends()],
    service: Annotated[OAuthService, Depends()],
):
    """Naver OAuth 인증 URL을 생성합니다."""
    result = await service.authorize("naver", params)
    return {"success": True, "data": result}


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
    service: Annotated[OAuthService, Depends()],
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
        return {"success": True, "data": {"user": user}}
    except Exception:
        # OAuth 실패 시 프론트엔드 로그인 페이지로 리다이렉트
        settings = get_settings()
        return RedirectResponse(url=f"{settings.frontend_url}/login?error=oauth_failed")


@kakao_router.get(
    "/callback",
    summary="Kakao OAuth callback handler",
)
async def kakao_callback(
    code: str,
    state: str,
    request: Request,
    response: Response,
    service: Annotated[OAuthService, Depends()],
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
        return {"success": True, "data": {"user": user}}
    except Exception:
        # OAuth 실패 시 프론트엔드 로그인 페이지로 리다이렉트
        settings = get_settings()
        return RedirectResponse(url=f"{settings.frontend_url}/login?error=oauth_failed")


@naver_router.get(
    "/callback",
    summary="Naver OAuth callback handler",
)
async def naver_callback(
    code: str,
    state: str,
    request: Request,
    response: Response,
    service: Annotated[OAuthService, Depends()],
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
        return {"success": True, "data": {"user": user}}
    except Exception:
        # OAuth 실패 시 프론트엔드 로그인 페이지로 리다이렉트
        settings = get_settings()
        return RedirectResponse(url=f"{settings.frontend_url}/login?error=oauth_failed")
