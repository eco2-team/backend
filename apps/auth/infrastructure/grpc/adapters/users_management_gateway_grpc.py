"""UsersManagementGatewayGrpc Adapter.

users 도메인의 gRPC 서비스를 호출하는 어댑터입니다.

참고: https://rooftopsnow.tistory.com/127
"""

from __future__ import annotations

import logging
from uuid import UUID

from apps.auth.application.users.ports.users_management_gateway import (
    OAuthUserResult,
    UsersManagementGateway,
)
from apps.auth.infrastructure.grpc.client import UsersGrpcClient

logger = logging.getLogger(__name__)


class UsersManagementGatewayGrpc(UsersManagementGateway):
    """gRPC를 통한 UsersManagementGateway 구현.

    users 도메인의 gRPC 서비스와 통신합니다.
    """

    def __init__(self, client: UsersGrpcClient) -> None:
        self._client = client

    async def get_or_create_from_oauth(
        self,
        *,
        provider: str,
        provider_user_id: str,
        email: str | None = None,
        nickname: str | None = None,
        profile_image_url: str | None = None,
    ) -> OAuthUserResult | None:
        """OAuth 프로필로 사용자 조회 또는 생성."""
        response = await self._client.get_or_create_from_oauth(
            provider=provider,
            provider_user_id=provider_user_id,
            email=email,
            nickname=nickname,
            profile_image_url=profile_image_url,
        )

        if response is None:
            logger.warning(
                "Failed to get_or_create_from_oauth via gRPC",
                extra={"provider": provider},
            )
            return None

        return OAuthUserResult(
            user_id=UUID(response.user.id),
            username=response.user.username or None,
            nickname=response.user.nickname or None,
            profile_image_url=response.user.profile_image_url or None,
            is_new_user=response.is_new_user,
        )

    async def update_login_time(
        self,
        *,
        user_id: UUID,
        provider: str,
        provider_user_id: str,
    ) -> bool:
        """로그인 시간 업데이트."""
        return await self._client.update_login_time(
            user_id=str(user_id),
            provider=provider,
            provider_user_id=provider_user_id,
        )

    @property
    def circuit_state(self) -> str:
        """현재 Circuit Breaker 상태."""
        return self._client.circuit_state
