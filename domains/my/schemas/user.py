from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class SocialAccountProfile(ORMModel):
    provider: str
    provider_user_id: str
    email: Optional[EmailStr] = None
    username: Optional[str] = None
    nickname: Optional[str] = None
    profile_image_url: Optional[str] = None
    last_login_at: Optional[datetime] = None


class UserProfile(ORMModel):
    id: int
    auth_user_id: UUID
    username: Optional[str] = None
    name: Optional[str] = None
    profile_image_url: Optional[str] = None
    created_at: datetime
    primary_provider: Optional[str] = None
    primary_email: Optional[EmailStr] = None
    social_accounts: list[SocialAccountProfile] = Field(default_factory=list)


class UserUpdate(BaseModel):
    username: Optional[str] = None
    profile_image_url: Optional[str] = None


class ProfileImageUpdateRequest(BaseModel):
    profile_image_url: Optional[str] = None


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
