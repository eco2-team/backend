"""GetProfile Query.

프로필 조회 Query(지휘자)입니다.

Architecture:
    - Query(지휘자): GetProfileQuery
    - Services(연주자): ProfileBuilder (순수 DTO 구성)
    - Ports(인프라): ProfileQueryGateway, SocialAccountQueryGateway
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from uuid import UUID

from apps.users.application.profile.dto import UserProfile
from apps.users.application.profile.exceptions import UserNotFoundError

if TYPE_CHECKING:
    from apps.users.application.identity.ports import SocialAccountQueryGateway
    from apps.users.application.profile.ports import ProfileQueryGateway
    from apps.users.application.profile.services import ProfileBuilder

logger = logging.getLogger(__name__)


class GetProfileQuery:
    """사용자 프로필 조회 Query (지휘자).

    프로필 조회 플로우를 오케스트레이션합니다.

    Workflow:
        1. 사용자 조회 (ProfileQueryGateway)
        2. 소셜 계정 조회 (SocialAccountQueryGateway)
        3. DTO 구성 (ProfileBuilder)

    Dependencies:
        Ports (인프라):
            - profile_gateway: 사용자 데이터 조회
            - social_account_gateway: 소셜 계정 데이터 조회

        Services (연주자):
            - profile_builder: 순수 DTO 구성
    """

    def __init__(
        self,
        # Ports (인프라)
        profile_gateway: "ProfileQueryGateway",
        social_account_gateway: "SocialAccountQueryGateway",
        # Services (연주자)
        profile_builder: "ProfileBuilder",
    ) -> None:
        self._profile_gateway = profile_gateway
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
            "Profile query executed",
            extra={"user_id": str(user_id), "provider": provider},
        )

        # 1. 사용자 조회 (Port 직접 호출)
        user = await self._profile_gateway.get_by_id(user_id)
        if user is None:
            raise UserNotFoundError(user_id)

        # 2. 소셜 계정 조회 (Port 직접 호출)
        accounts = await self._social_account_gateway.list_by_user_id(user_id)

        # 3. DTO 구성 (Service - 순수 로직)
        return self._profile_builder.build(user, accounts, provider)
