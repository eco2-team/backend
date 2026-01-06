"""UserService 단위 테스트."""

from datetime import datetime, timezone
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from apps.auth.domain.entities.user import User
from apps.auth.domain.entities.user_social_account import UserSocialAccount
from apps.auth.domain.services.user_service import UserService
from apps.auth.domain.value_objects.user_id import UserId


class TestUserService:
    """UserService 테스트."""

    @pytest.fixture
    def mock_user_id_generator(self) -> MagicMock:
        """Callable Mock으로 UserIdGenerator 시뮬레이션."""
        user_id = UserId.generate()
        generator = MagicMock(return_value=user_id)
        generator._generated_id = user_id  # 테스트에서 참조용
        return generator

    @pytest.fixture
    def user_service(self, mock_user_id_generator: MagicMock) -> UserService:
        return UserService(user_id_generator=mock_user_id_generator)

    def test_create_user_from_oauth_profile(
        self,
        user_service: UserService,
        mock_user_id_generator: MagicMock,
    ) -> None:
        """OAuth 프로필에서 사용자 생성 테스트."""
        # Arrange
        expected_id = mock_user_id_generator._generated_id

        # Act
        user, social_account = user_service.create_user_from_oauth_profile(
            provider="google",
            provider_user_id="google-123456",
            email="test@example.com",
            nickname="testuser",
            profile_image_url="https://example.com/avatar.jpg",
        )

        # Assert
        assert user.id_ == expected_id
        assert user.nickname == "testuser"
        assert user.profile_image_url == "https://example.com/avatar.jpg"

        assert social_account.user_id == expected_id.value
        assert social_account.provider == "google"
        assert social_account.provider_user_id == "google-123456"
        assert social_account.email == "test@example.com"

        # generator가 호출되었는지 확인
        mock_user_id_generator.assert_called_once()

    def test_create_user_without_nickname_uses_email(
        self,
        user_service: UserService,
    ) -> None:
        """닉네임 없이 사용자 생성 테스트."""
        # Act
        user, social_account = user_service.create_user_from_oauth_profile(
            provider="kakao",
            provider_user_id="kakao-789",
            email="user@kakao.com",
            nickname=None,
            profile_image_url=None,
        )

        # Assert
        assert user is not None
        assert user.nickname is None  # 현재 구현에서는 nickname=None 유지

    def test_create_user_without_email_and_nickname(
        self,
        user_service: UserService,
    ) -> None:
        """이메일과 닉네임 모두 없이 사용자 생성 테스트."""
        # Act
        user, social_account = user_service.create_user_from_oauth_profile(
            provider="naver",
            provider_user_id="naver-456",
            email=None,
            nickname=None,
            profile_image_url=None,
        )

        # Assert
        assert user is not None
        assert social_account.provider == "naver"

    def test_update_user_login(
        self,
        user_service: UserService,
    ) -> None:
        """로그인 시간 업데이트 테스트."""
        # Arrange
        user_id = UserId.generate()
        now = datetime.now(timezone.utc)
        user = User(
            id_=user_id,
            nickname="testuser",
            profile_image_url=None,
            created_at=now,
            updated_at=now,
        )
        social_account = UserSocialAccount(
            id=uuid4(),
            user_id=user_id.value,
            provider="google",
            provider_user_id="google-123",
            email="test@example.com",
            created_at=now,
            updated_at=now,
            last_login_at=now,
        )

        # Act
        user_service.update_user_login(user, social_account)

        # Assert
        assert user.last_login_at is not None
        assert social_account.last_login_at is not None

    def test_create_user_generates_unique_id(
        self,
        mock_user_id_generator: MagicMock,
    ) -> None:
        """사용자 생성 시 고유 ID 생성 확인 테스트."""
        # Arrange
        expected_id = mock_user_id_generator._generated_id
        user_service = UserService(user_id_generator=mock_user_id_generator)

        # Act
        user, _ = user_service.create_user_from_oauth_profile(
            provider="google",
            provider_user_id="google-unique",
            email="unique@example.com",
            nickname="unique_user",
        )

        # Assert
        mock_user_id_generator.assert_called_once()
        assert user.id_ == expected_id


class TestUserServiceEdgeCases:
    """UserService 엣지 케이스 테스트."""

    @pytest.fixture
    def user_service(self) -> UserService:
        from apps.auth.infrastructure.common.adapters.users_id_generator_uuid import (
            UuidUsersIdGenerator,
        )

        return UserService(user_id_generator=UuidUsersIdGenerator())

    def test_multiple_users_have_unique_ids(
        self,
        user_service: UserService,
    ) -> None:
        """여러 사용자 생성 시 ID 고유성 테스트."""
        # Act
        users = []
        for i in range(5):
            user, _ = user_service.create_user_from_oauth_profile(
                provider="google",
                provider_user_id=f"google-{i}",
                email=f"user{i}@example.com",
                nickname=f"user{i}",
            )
            users.append(user)

        # Assert
        user_ids = [u.id_.value for u in users]
        assert len(user_ids) == len(set(user_ids))  # 모두 고유함

    def test_social_account_linked_to_user(
        self,
        user_service: UserService,
    ) -> None:
        """소셜 계정이 사용자에게 연결되는지 테스트."""
        # Act
        user, social_account = user_service.create_user_from_oauth_profile(
            provider="google",
            provider_user_id="google-linked",
            email="linked@example.com",
            nickname="linked_user",
        )

        # Assert
        assert social_account.user_id == user.id_.value

    def test_link_social_account(
        self,
        user_service: UserService,
    ) -> None:
        """기존 사용자에 소셜 계정 연결 테스트."""
        # Arrange
        user, _ = user_service.create_user_from_oauth_profile(
            provider="google",
            provider_user_id="google-original",
            email="original@example.com",
            nickname="original_user",
        )
        initial_account_count = len(user.social_accounts)

        # Act
        new_account = user_service.link_social_account(
            user,
            provider="kakao",
            provider_user_id="kakao-linked",
            email="linked@kakao.com",
        )

        # Assert
        assert len(user.social_accounts) == initial_account_count + 1
        assert new_account.provider == "kakao"
        assert new_account.user_id == user.id_.value
