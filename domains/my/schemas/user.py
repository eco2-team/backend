from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class UserProfile(ORMModel):
    username: str
    nickname: str
    phone_number: Optional[str] = None
    email: Optional[EmailStr] = None
    profile_image_url: str
    provider: str
    last_login_at: Optional[datetime] = None


class UserUpdate(BaseModel):
    username: Optional[str] = None
    nickname: Optional[str] = None
    phone_number: Optional[str] = None
    email: Optional[EmailStr] = None
    profile_image_url: Optional[str] = None


class ProfileImageUpdateRequest(BaseModel):
    profile_image_url: Optional[str] = None


class ProfileImageUpdateResponse(BaseModel):
    success: bool = True


class UserCharacter(BaseModel):
    id: UUID
    code: str
    name: str
    type: str
    dialog: str
    acquired_at: datetime


class CharacterOwnershipStatus(BaseModel):
    character_name: str
    owned: bool
