"""Application schemas (DTOs)."""

from domains.auth.application.schemas.auth import (
    AuthorizationResponse,
    AuthorizationSuccessResponse,
    LoginData,
    LoginSuccessResponse,
    LogoutData,
    LogoutSuccessResponse,
    OAuthAuthorizeParams,
    OAuthLoginRequest,
    SocialAccount,
    User,
    UserSuccessResponse,
)
from domains.auth.application.schemas.common import ErrorDetail, ErrorResponse, SuccessResponse
from domains.auth.application.schemas.oauth import OAuthProfile

__all__ = [
    "AuthorizationResponse",
    "AuthorizationSuccessResponse",
    "ErrorDetail",
    "ErrorResponse",
    "LoginData",
    "LoginSuccessResponse",
    "LogoutData",
    "LogoutSuccessResponse",
    "OAuthAuthorizeParams",
    "OAuthLoginRequest",
    "OAuthProfile",
    "SocialAccount",
    "SuccessResponse",
    "User",
    "UserSuccessResponse",
]
