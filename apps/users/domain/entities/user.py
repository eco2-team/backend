"""User entity - Core domain object for user profile."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID


@dataclass
class User:
    """사용자 엔티티.

    users.users 테이블에 매핑됩니다.
    user_profile.users 구조를 복제하여 하위 호환성을 유지합니다.
    """

    id: int | None = None
    auth_user_id: UUID | None = None
    username: str | None = None
    nickname: str | None = None
    name: str | None = None
    email: str | None = None
    phone_number: str | None = None
    profile_image_url: str | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)

    def update_profile(
        self,
        *,
        username: str | None = None,
        nickname: str | None = None,
        name: str | None = None,
        phone_number: str | None = None,
        profile_image_url: str | None = None,
    ) -> None:
        """프로필 정보를 업데이트합니다."""
        if username is not None:
            self.username = username
        if nickname is not None:
            self.nickname = nickname
        if name is not None:
            self.name = name
        if phone_number is not None:
            self.phone_number = phone_number
        if profile_image_url is not None:
            self.profile_image_url = profile_image_url
