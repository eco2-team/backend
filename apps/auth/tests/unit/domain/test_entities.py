"""Domain Entity Tests."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from apps.auth.domain.entities.user import User
from apps.auth.domain.entities.user_social_account import UserSocialAccount
from apps.auth.domain.value_objects.user_id import UserId


class TestUser:
    """User 엔티티 테스트."""

    def test_create_user(self) -> None:
        """User 생성 테스트."""
        # Arrange
        user_id = UserId.generate()
        now = datetime.now(timezone.utc)

        # Act
        user = User(
            id_=user_id,
            nickname="test",
            profile_image_url=None,
            created_at=now,
            updated_at=now,
        )

        # Assert
        assert user.id_ == user_id
        assert user.nickname == "test"
        assert user.profile_image_url is None

    def test_user_equality(self) -> None:
        """같은 ID의 User는 동일."""
        # Arrange
        user_id = UserId.generate()
        now = datetime.now(timezone.utc)

        # Act
        user1 = User(
            id_=user_id,
            nickname="test1",
            created_at=now,
            updated_at=now,
        )
        user2 = User(
            id_=user_id,
            nickname="test2",
            created_at=now,
            updated_at=now,
        )

        # Assert
        assert user1 == user2
        assert hash(user1) == hash(user2)

    def test_user_inequality(self) -> None:
        """다른 ID의 User는 다름."""
        # Arrange
        now = datetime.now(timezone.utc)

        # Act
        user1 = User(
            id_=UserId.generate(),
            nickname="test",
            created_at=now,
            updated_at=now,
        )
        user2 = User(
            id_=UserId.generate(),
            nickname="test",
            created_at=now,
            updated_at=now,
        )

        # Assert
        assert user1 != user2

    def test_update_login_time(self) -> None:
        """로그인 시간 업데이트 테스트."""
        # Arrange
        now = datetime.now(timezone.utc)
        user = User(
            id_=UserId.generate(),
            nickname="test",
            created_at=now,
            updated_at=now,
        )
        assert user.last_login_at is None

        # Act
        user.update_login_time()

        # Assert
        assert user.last_login_at is not None


class TestUserSocialAccount:
    """UserSocialAccount 엔티티 테스트."""

    def test_create_social_account(self) -> None:
        """소셜 계정 생성 테스트."""
        # Arrange
        account_id = uuid.uuid4()
        user_id = uuid.uuid4()
        now = datetime.now(timezone.utc)

        # Act
        account = UserSocialAccount(
            id=account_id,
            user_id=user_id,
            provider="google",
            provider_user_id="google123",
            created_at=now,
            updated_at=now,
        )

        # Assert
        assert account.id == account_id
        assert account.user_id == user_id
        assert account.provider == "google"
        assert account.provider_user_id == "google123"

    def test_update_login_time(self) -> None:
        """로그인 시간 업데이트 테스트."""
        # Arrange
        now = datetime.now(timezone.utc)
        account = UserSocialAccount(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            provider="kakao",
            provider_user_id="kakao123",
            created_at=now,
            updated_at=now,
        )

        # Act
        account.update_login_time()

        # Assert
        assert account.last_login_at is not None
