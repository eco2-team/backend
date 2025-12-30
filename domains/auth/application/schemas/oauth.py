from typing import Optional

from pydantic import BaseModel, EmailStr, HttpUrl


class OAuthProfile(BaseModel):
    provider: str
    provider_user_id: str
    email: Optional[EmailStr] = None
    name: Optional[str] = None
    nickname: Optional[str] = None
    profile_image_url: Optional[HttpUrl] = None
    phone_number: Optional[str] = None
