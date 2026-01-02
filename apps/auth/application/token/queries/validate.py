"""ValidateToken Query.

토큰 검증 Query Service입니다.

Architecture:
    - QueryService: ValidateTokenQueryService
    - Services(연주자): TokenService
    - Ports(인프라): UsersQueryGateway
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import UUID

from apps.auth.domain.enums.token_type import TokenType
from apps.auth.domain.exceptions.auth import TokenRevokedError
from apps.auth.domain.exceptions.user import UserNotFoundError
from apps.auth.domain.value_objects.user_id import UserId

if TYPE_CHECKING:
    # Services (연주자)
    from apps.auth.application.token.services import TokenService

    # Ports (인프라)
    from apps.auth.application.users.ports import UsersQueryGateway


@dataclass(frozen=True, slots=True)
class ValidatedUser:
    """검증된 사용자 정보."""

    user_id: UUID
    nickname: str | None
    email: str | None
    profile_image_url: str | None
    provider: str


class ValidateTokenQueryService:
    """토큰 검증 Query Service.

    Access 토큰을 검증하고 사용자 정보를 반환합니다.

    Dependencies:
        Services (연주자):
            - token_service: 토큰 검증 및 블랙리스트 확인

        Ports (인프라):
            - user_query_gateway: 사용자 조회
    """

    def __init__(
        self,
        # Services (연주자)
        token_service: "TokenService",
        # Ports (인프라)
        user_query_gateway: "UsersQueryGateway",
    ) -> None:
        self._token_service = token_service
        self._user_query_gateway = user_query_gateway

    async def execute(self, access_token: str) -> ValidatedUser:
        """토큰을 검증하고 사용자 정보를 조회합니다.

        Args:
            access_token: Access 토큰

        Returns:
            검증된 사용자 정보

        Raises:
            InvalidTokenError: 유효하지 않은 토큰
            TokenRevokedError: 폐기된 토큰
            UserNotFoundError: 사용자를 찾을 수 없음
        """
        # 1. 토큰 디코딩 및 검증 (Service에 위임)
        payload = self._token_service.decode_and_validate(
            access_token,
            expected_type=TokenType.ACCESS,
        )

        # 2. 블랙리스트 확인 (Service에 위임)
        if await self._token_service.is_blacklisted(payload.jti):
            raise TokenRevokedError(payload.jti)

        # 3. 사용자 조회 (Port 직접 사용 - 외부 도메인)
        user = await self._user_query_gateway.get_by_id(UserId(value=payload.user_id.value))
        if not user:
            raise UserNotFoundError(str(payload.user_id.value))

        return ValidatedUser(
            user_id=user.id_.value,
            nickname=user.nickname,
            email=user.email,
            profile_image_url=user.profile_image_url,
            provider=payload.provider,
        )
