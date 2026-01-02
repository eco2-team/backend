"""User-related HTTP schemas."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class UserProfileResponse(BaseModel):
    """사용자 프로필 응답 스키마."""

    display_name: str = Field(..., description="화면 표시명 (nickname 또는 name)")
    nickname: str = Field(..., description="닉네임")
    phone_number: str | None = Field(None, description="전화번호")
    provider: str = Field(..., description="OAuth 프로바이더")
    last_login_at: datetime | None = Field(None, description="마지막 로그인 시각")

    model_config = {"from_attributes": True}


class UserUpdateRequest(BaseModel):
    """사용자 프로필 수정 요청 스키마."""

    nickname: str | None = Field(None, min_length=1, max_length=120, description="닉네임")
    phone_number: str | None = Field(None, min_length=10, max_length=20, description="전화번호")


class UserCharacterResponse(BaseModel):
    """사용자 캐릭터 응답 스키마."""

    id: UUID = Field(..., description="캐릭터 소유 ID")
    character_id: UUID = Field(..., description="캐릭터 ID")
    character_code: str = Field(..., description="캐릭터 코드")
    character_name: str = Field(..., description="캐릭터 이름")
    character_type: str | None = Field(None, description="캐릭터 타입")
    character_dialog: str | None = Field(None, description="캐릭터 대사")
    source: str | None = Field(None, description="획득 경로")
    status: str = Field(..., description="소유 상태")
    acquired_at: datetime = Field(..., description="획득 시각")

    model_config = {"from_attributes": True}


class CharacterListResponse(BaseModel):
    """캐릭터 목록 응답 스키마."""

    characters: list[UserCharacterResponse] = Field(..., description="캐릭터 목록")
    total: int = Field(..., description="총 개수")


class CharacterOwnershipResponse(BaseModel):
    """캐릭터 소유 여부 응답 스키마."""

    character_code: str = Field(..., description="캐릭터 코드")
    owned: bool = Field(..., description="소유 여부")
    acquired_at: datetime | None = Field(None, description="획득 시각")
