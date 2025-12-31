"""User Entity.

ORM과 분리된 순수 도메인 엔티티입니다.
SQLAlchemy 매핑은 infrastructure/persistence_postgres/mappings/user.py에서 정의합니다.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from apps.auth.domain.entities.base import Entity
from apps.auth.domain.value_objects.user_id import UserId

if TYPE_CHECKING:
    from apps.auth.domain.entities.user_social_account import UserSocialAccount


class User(Entity[UserId]):
    """사용자 엔티티.

    Attributes:
        id_: 사용자 고유 식별자
        username: 사용자명 (선택)
        nickname: 닉네임 (선택)
        profile_image_url: 프로필 이미지 URL (선택)
        phone_number: 전화번호 (선택)
        created_at: 생성 시각
        updated_at: 수정 시각
        last_login_at: 마지막 로그인 시각 (선택)
        social_accounts: 연결된 소셜 계정 목록
    """

    __slots__ = (
        "username",
        "nickname",
        "profile_image_url",
        "phone_number",
        "created_at",
        "updated_at",
        "last_login_at",
        "social_accounts",
    )

    def __init__(
        self,
        *,
        id_: UserId,
        username: str | None = None,
        nickname: str | None = None,
        profile_image_url: str | None = None,
        phone_number: str | None = None,
        created_at: datetime,
        updated_at: datetime,
        last_login_at: datetime | None = None,
        social_accounts: list["UserSocialAccount"] | None = None,
    ) -> None:
        super().__init__(id_=id_)
        self.username = username
        self.nickname = nickname
        self.profile_image_url = profile_image_url
        self.phone_number = phone_number
        self.created_at = created_at
        self.updated_at = updated_at
        self.last_login_at = last_login_at
        self.social_accounts = social_accounts or []

    @property
    def primary_social_account(self) -> "UserSocialAccount | None":
        """가장 최근에 로그인한 소셜 계정 반환."""
        if not self.social_accounts:
            return None
        return max(
            self.social_accounts,
            key=lambda acc: (
                acc.last_login_at or acc.updated_at or acc.created_at,
                acc.created_at,
            ),
        )

    @property
    def provider(self) -> str | None:
        """주 소셜 계정의 프로바이더."""
        primary = self.primary_social_account
        return primary.provider if primary else None

    @property
    def email(self) -> str | None:
        """주 소셜 계정의 이메일."""
        primary = self.primary_social_account
        return primary.email if primary else None

    def update_login_time(self) -> None:
        """로그인 시간 업데이트."""
        self.last_login_at = datetime.now(timezone.utc)

    def __repr__(self) -> str:
        return f"User(id_={self.id_}, username={self.username!r})"
