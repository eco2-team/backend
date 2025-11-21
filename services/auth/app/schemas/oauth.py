from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, HttpUrl


class OAuthProfile(BaseModel):
    provider: str
    provider_user_id: str
    email: Optional[EmailStr] = None
    name: Optional[str] = None
    nickname: Optional[str] = None
    profile_image_url: Optional[HttpUrl] = None


class OAuthAuthorizeParams(BaseModel):
    redirect_uri: Optional[HttpUrl] = None
    scope: Optional[str] = None
    device_id: Optional[str] = Field(default=None, max_length=120)


class OAuthLoginRequest(BaseModel):
    code: str = Field(..., min_length=1)
    state: str = Field(..., min_length=8)
    redirect_uri: Optional[HttpUrl] = None


class OAuthAuthorizeResponse(BaseModel):
    success: bool = True
    data: dict
