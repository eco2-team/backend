from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, HttpUrl

from domain.auth.schemas.common import SuccessResponse


class AuthorizationResponse(BaseModel):
    provider: str
    state: str
    authorization_url: HttpUrl
    expires_at: datetime


class AuthorizationSuccessResponse(SuccessResponse[AuthorizationResponse]):
    """Standardized success response for authorization."""

    pass


class OAuthAuthorizeParams(BaseModel):
    redirect_uri: Optional[HttpUrl] = None
    scope: Optional[str] = None
    device_id: Optional[str] = Field(default=None, max_length=120)


class OAuthLoginRequest(BaseModel):
    code: str = Field(..., min_length=1)
    state: str = Field(..., min_length=8)
    redirect_uri: Optional[HttpUrl] = None


class LogoutData(BaseModel):
    """Logout response data."""

    message: str = "Successfully logged out"


class LogoutSuccessResponse(SuccessResponse[LogoutData]):
    """Standardized success response for logout."""

    pass


class User(BaseModel):
    id: UUID
    provider: str
    email: Optional[EmailStr] = None
    username: Optional[str] = None
    nickname: Optional[str] = None
    profile_image_url: Optional[HttpUrl] = None
    created_at: datetime
    last_login_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class UserSuccessResponse(SuccessResponse[User]):
    """Standardized success response for user data."""

    pass


class LoginData(BaseModel):
    """Login response data."""

    user: User


class LoginSuccessResponse(SuccessResponse[LoginData]):
    """Standardized success response for login."""

    pass
