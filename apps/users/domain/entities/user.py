"""User entity - Core domain object for user profile."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID


@dataclass
class User:
    """사용자 엔티티.

    users.users 테이블에 매핑됩니다.
    auth.users + user_profile.users 통합 구조입니다.

    Note:
        - id는 UUID (기존 auth.users.id를 그대로 사용)
        - auth_user_id 컬럼은 제거됨 (id가 곧 user_id)
    """

    id: UUID | None = None
    username: str | None = None
    nickname: str | None = None
    name: str | None = None
    email: str | None = None
    phone_number: str | None = None
    profile_image_url: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_login_at: datetime | None = None

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
        self.updated_at = datetime.now(timezone.utc)

    def update_login_time(self) -> None:
        """마지막 로그인 시간을 업데이트합니다."""
        now = datetime.now(timezone.utc)
        self.last_login_at = now
        self.updated_at = now
