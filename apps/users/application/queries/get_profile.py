"""Get profile query - Retrieves user profile."""

from __future__ import annotations

import logging
from uuid import UUID

from apps.users.application.common.dto import UserProfile
from apps.users.application.common.ports import (
    SocialAccountQueryGateway,
    UserCommandGateway,
    UserQueryGateway,
)
from apps.users.application.common.services import ProfileBuilder
from apps.users.domain.entities.user import User

logger = logging.getLogger(__name__)


class GetProfileQuery:
    """사용자 프로필 조회 쿼리.

    기존 MyService.get_current_user를 대체합니다.
    """

    def __init__(
        self,
        user_query_gateway: UserQueryGateway,
        user_command_gateway: UserCommandGateway,
        social_account_gateway: SocialAccountQueryGateway,
        profile_builder: ProfileBuilder,
    ) -> None:
        self._user_query = user_query_gateway
        self._user_command = user_command_gateway
        self._social_account_gateway = social_account_gateway
        self._profile_builder = profile_builder

    async def execute(self, auth_user_id: UUID, provider: str) -> UserProfile:
        """사용자 프로필을 조회합니다.

        Args:
            auth_user_id: 인증 사용자 ID (auth.users.id)
            provider: 현재 로그인에 사용된 OAuth 프로바이더

        Returns:
            UserProfile: 사용자 프로필 DTO
        """
        logger.info(
            "Profile fetched",
            extra={"user_id": str(auth_user_id), "provider": provider},
        )

        user = await self._get_or_create_user(auth_user_id)
        accounts = await self._social_account_gateway.list_by_user_id(auth_user_id)

        return self._profile_builder.build(user, accounts, provider)

    async def _get_or_create_user(self, auth_user_id: UUID) -> User:
        """사용자를 조회하거나 생성합니다."""
        user = await self._user_query.get_by_auth_user_id(auth_user_id)
        if user is None:
            user = User(auth_user_id=auth_user_id)
            user = await self._user_command.create(user)
        return user
