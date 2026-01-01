"""Get profile query - Retrieves user profile."""

from __future__ import annotations

import logging
from uuid import UUID

from apps.users.application.common.dto import UserProfile
from apps.users.application.common.exceptions.user import UserNotFoundError
from apps.users.application.common.ports import (
    SocialAccountQueryGateway,
    UserQueryGateway,
)
from apps.users.application.common.services import ProfileBuilder

logger = logging.getLogger(__name__)


class GetProfileQuery:
    """사용자 프로필 조회 쿼리.

    기존 MyService.get_current_user를 대체합니다.

    Note:
        통합 스키마에서 사용자는 OAuth 로그인 시 gRPC를 통해 생성됩니다.
        프로필 조회 시점에는 사용자가 이미 존재해야 합니다.
    """

    def __init__(
        self,
        user_query_gateway: UserQueryGateway,
        social_account_gateway: SocialAccountQueryGateway,
        profile_builder: ProfileBuilder,
    ) -> None:
        self._user_query = user_query_gateway
        self._social_account_gateway = social_account_gateway
        self._profile_builder = profile_builder

    async def execute(self, user_id: UUID, provider: str) -> UserProfile:
        """사용자 프로필을 조회합니다.

        Args:
            user_id: 사용자 ID (users.users.id)
            provider: 현재 로그인에 사용된 OAuth 프로바이더

        Returns:
            UserProfile: 사용자 프로필 DTO

        Raises:
            UserNotFoundError: 사용자가 존재하지 않는 경우
        """
        logger.info(
            "Profile fetched",
            extra={"user_id": str(user_id), "provider": provider},
        )

        user = await self._user_query.get_by_id(user_id)
        if user is None:
            raise UserNotFoundError(user_id)

        accounts = await self._social_account_gateway.list_by_user_id(user_id)

        return self._profile_builder.build(user, accounts, provider)
