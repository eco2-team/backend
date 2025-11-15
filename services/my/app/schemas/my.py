from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr


class UserProfile(BaseModel):
    id: int
    email: EmailStr
    username: str
    avatar_url: Optional[str] = None
    points: int = 0
    level: int = 1
    created_at: datetime


class UserUpdate(BaseModel):
    username: Optional[str] = None
    avatar_url: Optional[str] = None


class ActivityEntry(BaseModel):
    id: int
    user_id: int
    action: str
    points_earned: int
    timestamp: datetime


class UserPoints(BaseModel):
    user_id: int
    total_points: int
    available_points: int
    used_points: int
