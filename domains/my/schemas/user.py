from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class UserProfile(ORMModel):
    id: int
    provider: str
    provider_user_id: str
    email: EmailStr
    username: str
    name: Optional[str] = None
    profile_image_url: Optional[str] = None
    created_at: datetime


class UserUpdate(BaseModel):
    username: Optional[str] = None
    name: Optional[str] = None
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
