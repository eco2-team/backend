"""RefreshTokens Command.

토큰 갱신 Use Case입니다.

Architecture:
    - UseCase(지휘자): RefreshTokensInteractor
    - Services(연주자): TokenService
    - Ports(인프라): UsersQueryGateway, BlacklistEventPublisher, TransactionManager
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from apps.auth.application.token.dto import (
    RefreshTokensRequest,
    RefreshTokensResponse,
)
from apps.auth.domain.enums.token_type import TokenType
from apps.auth.domain.exceptions.auth import TokenRevokedError
from apps.auth.domain.exceptions.user import UserNotFoundError
from apps.auth.domain.value_objects.user_id import UserId

if TYPE_CHECKING:
    # Services (연주자)
    # Ports (인프라)
    from apps.auth.application.common.ports import TransactionManager
    from apps.auth.application.token.ports import BlacklistEventPublisher
    from apps.auth.application.token.services import TokenService
    from apps.auth.application.users.ports import UsersQueryGateway

logger = logging.getLogger(__name__)


class RefreshTokensInteractor:
    """토큰 갱신 Interactor (지휘자).

    토큰 갱신 플로우를 오케스트레이션합니다.

    Workflow:
        1. Refresh 토큰 검증 (TokenService)
        2. 블랙리스트 확인 (TokenService)
        3. 세션 유효성 확인 (TokenService)
        4. 사용자 조회 (UsersQueryGateway)
        5. 기존 토큰 폐기 이벤트 발행 (BlacklistEventPublisher)
        6. 새 토큰 발급 및 세션 등록 (TokenService)
        7. 트랜잭션 커밋 (TransactionManager)

    Dependencies:
        Services (연주자):
            - token_service: 토큰 검증, 발급, 세션 관리

        Ports (인프라):
            - user_query_gateway: 사용자 조회
            - blacklist_publisher: 블랙리스트 이벤트 발행
            - transaction_manager: 트랜잭션 제어
    """

    def __init__(
        self,
        # Services (연주자)
        token_service: "TokenService",
        # Ports (인프라)
        user_query_gateway: "UsersQueryGateway",
        blacklist_publisher: "BlacklistEventPublisher",
        transaction_manager: "TransactionManager",
    ) -> None:
        # Services
        self._token_service = token_service
        # Ports
        self._user_query_gateway = user_query_gateway
        self._blacklist_publisher = blacklist_publisher
        self._transaction_manager = transaction_manager

    async def execute(self, request: RefreshTokensRequest) -> RefreshTokensResponse:
        """토큰을 갱신합니다.

        Args:
            request: 토큰 갱신 요청 DTO

        Returns:
            새 토큰 쌍을 담은 응답 DTO

        Raises:
            InvalidTokenError: 유효하지 않은 토큰
            TokenRevokedError: 폐기된 토큰
            UserNotFoundError: 사용자를 찾을 수 없음
        """
        # 1. Refresh 토큰 검증 (Service에 위임)
        payload = self._token_service.decode_and_validate(
            request.refresh_token,
            expected_type=TokenType.REFRESH,
        )

        # 2. 블랙리스트 확인 (Service에 위임)
        if await self._token_service.is_blacklisted(payload.jti):
            raise TokenRevokedError(payload.jti)

        # 3. 세션 유효성 확인 (Service에 위임)
        if not await self._token_service.validate_session(payload.user_id.value, payload.jti):
            raise TokenRevokedError("Refresh token not found in store")

        # 4. 사용자 조회 (Port 직접 사용 - 외부 도메인)
        user = await self._user_query_gateway.get_by_id(UserId(value=payload.user_id.value))
        if not user:
            raise UserNotFoundError(str(payload.user_id.value))

        # 5. 기존 토큰 폐기 이벤트 발행 (Port 직접 사용 - 이벤트 발행)
        await self._blacklist_publisher.publish_add(payload, reason="token_rotated")

        # 6. 새 토큰 발급 (기존 세션 폐기 + 새 세션 등록)
        token_result = await self._token_service.refresh_tokens(
            user_id=user.id_.value,
            old_refresh_jti=payload.jti,
            provider=payload.provider,
        )

        # 7. 트랜잭션 커밋
        await self._transaction_manager.commit()

        logger.info(f"Session refreshed: user_id={user.id_}")

        return RefreshTokensResponse(
            user_id=user.id_.value,
            access_token=token_result.access_token,
            refresh_token=token_result.refresh_token,
            access_expires_at=token_result.access_expires_at,
            refresh_expires_at=token_result.refresh_expires_at,
        )
