"""OAuth related DTOs."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True, slots=True)
class OAuthUserRequest:
    """OAuth 사용자 조회/생성 요청 DTO."""

    provider: str
    provider_user_id: str
    email: str | None = None
    nickname: str | None = None
    profile_image_url: str | None = None


@dataclass(frozen=True, slots=True)
class OAuthUserResult:
    """OAuth 사용자 조회/생성 결과 DTO."""

    user_id: UUID
    nickname: str | None
    email: str | None
    phone_number: str | None
    profile_image_url: str | None
    created_at: datetime
    updated_at: datetime
    last_login_at: datetime | None
    is_new_user: bool
    # Social account info
    social_account_id: UUID
    provider: str
    provider_user_id: str
    social_email: str | None
    social_last_login_at: datetime | None


@dataclass(frozen=True, slots=True)
class UpdateLoginTimeRequest:
    """로그인 시간 업데이트 요청 DTO."""

    user_id: UUID
    provider: str
    provider_user_id: str
