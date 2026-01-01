"""Test Factories.

테스트용 객체 생성 팩토리.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from apps.auth.domain.entities.user import User
from apps.auth.domain.entities.user_social_account import UserSocialAccount
from apps.auth.domain.value_objects.user_id import UserId


def create_user(
    *,
    user_id: UserId | None = None,
    nickname: str = "test-user",
    profile_image_url: str | None = None,
) -> User:
    """테스트용 User 생성."""
    now = datetime.now(timezone.utc)
    return User(
        id_=user_id or UserId.generate(),
        nickname=nickname,
        profile_image_url=profile_image_url,
        created_at=now,
        updated_at=now,
    )


def create_social_account(
    *,
    user_id: uuid.UUID | None = None,
    provider: str = "google",
    provider_user_id: str = "test-provider-id",
    email: str | None = "test@example.com",
) -> UserSocialAccount:
    """테스트용 UserSocialAccount 생성."""
    now = datetime.now(timezone.utc)
    return UserSocialAccount(
        id=uuid.uuid4(),
        user_id=user_id or uuid.uuid4(),
        provider=provider,
        provider_user_id=provider_user_id,
        email=email,
        created_at=now,
        updated_at=now,
    )
