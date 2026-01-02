"""SQLAlchemy implementation of identity gateways.

OAuth 로그인 관련 사용자 조회/생성 게이트웨이 구현체입니다.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.users.application.identity.ports.identity_gateway import UserWithSocialAccount
from apps.users.domain.entities.user import User
from apps.users.domain.enums import OAuthProvider
from apps.users.infrastructure.persistence_postgres.mappings.user_social_account import (
    UserSocialAccount,
)


class SqlaIdentityQueryGateway:
    """OAuth 식별 조회 게이트웨이 SQLAlchemy 구현.

    provider + provider_user_id로 사용자를 조회합니다.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_provider_identity(
        self,
        provider: str,
        provider_user_id: str,
    ) -> UserWithSocialAccount | None:
        """프로바이더 식별자로 사용자를 조회합니다."""
        # String → OAuthProvider enum 변환
        provider_enum = OAuthProvider(provider.lower())

        # 소셜 계정으로 조회 (Native SQL)
        result = await self._session.execute(
            select(UserSocialAccount).where(
                UserSocialAccount.provider == provider_enum,
                UserSocialAccount.provider_user_id == provider_user_id,
            )
        )
        social = result.scalar_one_or_none()

        if social is None:
            return None

        # 연결된 사용자 조회
        user_result = await self._session.execute(select(User).where(User.id == social.user_id))
        user = user_result.scalar_one_or_none()

        if user is None:
            return None

        return UserWithSocialAccount(user=user, social_account=social)


class SqlaIdentityCommandGateway:
    """OAuth 식별 수정 게이트웨이 SQLAlchemy 구현.

    사용자 및 소셜 계정을 생성/업데이트합니다.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_user_with_social_account(
        self,
        user_id: UUID,
        provider: str,
        provider_user_id: str,
        email: str | None = None,
        nickname: str | None = None,
        profile_image_url: str | None = None,
    ) -> UserWithSocialAccount:
        """사용자와 소셜 계정을 함께 생성합니다."""
        now = datetime.now(timezone.utc)

        # String → OAuthProvider enum 변환
        provider_enum = OAuthProvider(provider.lower())

        # 1. 사용자 생성
        user = User(
            id=user_id,
            nickname=nickname,
            email=email,
            profile_image_url=profile_image_url,
            created_at=now,
            updated_at=now,
        )
        self._session.add(user)

        # 2. 소셜 계정 생성
        social = UserSocialAccount(
            id=uuid4(),
            user_id=user_id,
            provider=provider_enum,
            provider_user_id=provider_user_id,
            email=email,
            created_at=now,
            updated_at=now,
        )
        self._session.add(social)

        await self._session.flush()
        return UserWithSocialAccount(user=user, social_account=social)

    async def update_social_login_time(
        self,
        user_id: UUID,
        provider: str,
        provider_user_id: str,
        login_time: datetime,
    ) -> None:
        """소셜 계정과 사용자의 로그인 시간을 업데이트합니다."""
        # String → OAuthProvider enum 변환
        provider_enum = OAuthProvider(provider.lower())

        # 1. 사용자 로그인 시간 업데이트
        user_result = await self._session.execute(select(User).where(User.id == user_id))
        user = user_result.scalar_one_or_none()
        if user:
            user.last_login_at = login_time
            user.updated_at = login_time

        # 2. 소셜 계정 로그인 시간 업데이트
        social_result = await self._session.execute(
            select(UserSocialAccount).where(
                UserSocialAccount.user_id == user_id,
                UserSocialAccount.provider == provider_enum,
                UserSocialAccount.provider_user_id == provider_user_id,
            )
        )
        social = social_result.scalar_one_or_none()
        if social:
            social.last_login_at = login_time
            social.updated_at = login_time

        await self._session.flush()
