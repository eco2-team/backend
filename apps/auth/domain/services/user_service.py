"""User Domain Service.

사용자 관련 도메인 비즈니스 로직을 담당합니다.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from apps.auth.domain.entities.user import User
from apps.auth.domain.entities.user_social_account import UserSocialAccount
from apps.auth.domain.ports.user_id_generator import UserIdGenerator


class UserService:
    """사용자 도메인 서비스.

    순수 도메인 로직만 포함합니다.
    외부 시스템 접근(DB, 캐시 등)은 Application Layer에서 처리합니다.
    """

    def __init__(self, user_id_generator: UserIdGenerator) -> None:
        self._user_id_generator = user_id_generator

    def create_user_from_oauth_profile(
        self,
        *,
        provider: str,
        provider_user_id: str,
        email: str | None = None,
        nickname: str | None = None,
        profile_image_url: str | None = None,
    ) -> tuple[User, UserSocialAccount]:
        """OAuth 프로필에서 새 사용자 생성.

        Args:
            provider: OAuth 프로바이더 (google, kakao, naver)
            provider_user_id: 프로바이더에서의 사용자 ID
            email: 이메일 (선택)
            nickname: 닉네임 (선택)
            profile_image_url: 프로필 이미지 URL (선택)

        Returns:
            생성된 (User, UserSocialAccount) 튜플
        """
        now = datetime.now(timezone.utc)
        user_id = self._user_id_generator()

        user = User(
            id_=user_id,
            username=None,
            nickname=nickname,
            profile_image_url=profile_image_url,
            phone_number=None,
            created_at=now,
            updated_at=now,
            last_login_at=now,
        )

        social_account = UserSocialAccount(
            id=uuid4(),
            user_id=user_id.value,
            provider=provider,
            provider_user_id=provider_user_id,
            email=email,
            last_login_at=now,
            created_at=now,
            updated_at=now,
        )

        user.social_accounts = [social_account]

        return user, social_account

    def link_social_account(
        self,
        user: User,
        *,
        provider: str,
        provider_user_id: str,
        email: str | None = None,
    ) -> UserSocialAccount:
        """기존 사용자에 소셜 계정 연결.

        Args:
            user: 연결할 사용자
            provider: OAuth 프로바이더
            provider_user_id: 프로바이더에서의 사용자 ID
            email: 이메일 (선택)

        Returns:
            생성된 UserSocialAccount
        """
        now = datetime.now(timezone.utc)

        social_account = UserSocialAccount(
            id=uuid4(),
            user_id=user.id_.value,
            provider=provider,
            provider_user_id=provider_user_id,
            email=email,
            last_login_at=now,
            created_at=now,
            updated_at=now,
        )

        user.social_accounts.append(social_account)

        return social_account

    def update_user_login(self, user: User, social_account: UserSocialAccount) -> None:
        """로그인 시간 업데이트.

        Args:
            user: 로그인한 사용자
            social_account: 사용된 소셜 계정
        """
        user.update_login_time()
        social_account.update_login_time()
