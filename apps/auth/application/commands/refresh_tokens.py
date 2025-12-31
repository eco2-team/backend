"""RefreshTokens Command.

토큰 갱신 Use Case입니다.
"""

from __future__ import annotations

import logging

from apps.auth.domain.enums.token_type import TokenType
from apps.auth.domain.exceptions.user import UserNotFoundError
from apps.auth.domain.exceptions.auth import TokenRevokedError
from apps.auth.application.common.dto.auth import (
    RefreshTokensRequest,
    RefreshTokensResponse,
)
from apps.auth.application.common.ports.token_service import TokenService
from apps.auth.application.common.ports.token_blacklist import TokenBlacklist
from apps.auth.application.common.ports.blacklist_event_publisher import (
    BlacklistEventPublisher,
)
from apps.auth.application.common.ports.user_token_store import UserTokenStore
from apps.auth.application.common.ports.user_query_gateway import UserQueryGateway
from apps.auth.application.common.ports.transaction_manager import TransactionManager
from apps.auth.domain.value_objects.user_id import UserId

logger = logging.getLogger(__name__)


class RefreshTokensInteractor:
    """토큰 갱신 Interactor.

    토큰 갱신 플로우:
    1. Refresh 토큰 검증
    2. 블랙리스트 확인
    3. 사용자 토큰 저장소 확인
    4. 사용자 조회
    5. 기존 토큰 폐기 (이벤트 발행)
    6. 새 토큰 발급
    7. 새 토큰 저장
    """

    def __init__(
        self,
        token_service: TokenService,
        token_blacklist: TokenBlacklist,
        blacklist_publisher: BlacklistEventPublisher,
        user_token_store: UserTokenStore,
        user_query_gateway: UserQueryGateway,
        transaction_manager: TransactionManager,
    ) -> None:
        self._token_service = token_service
        self._token_blacklist = token_blacklist
        self._blacklist_publisher = blacklist_publisher
        self._user_token_store = user_token_store
        self._user_query_gateway = user_query_gateway
        self._transaction_manager = transaction_manager

    async def execute(self, request: RefreshTokensRequest) -> RefreshTokensResponse:
        """토큰 갱신.

        Args:
            request: 토큰 갱신 요청 DTO

        Returns:
            새 토큰 쌍을 담은 응답 DTO

        Raises:
            InvalidTokenError: 유효하지 않은 토큰
            TokenRevokedError: 폐기된 토큰
            UserNotFoundError: 사용자를 찾을 수 없음
        """
        # 1. Refresh 토큰 검증
        payload = self._token_service.decode(request.refresh_token)
        self._token_service.ensure_type(payload, TokenType.REFRESH)

        # 2. 블랙리스트 확인 (읽기 - Redis 직접 조회)
        if await self._token_blacklist.contains(payload.jti):
            raise TokenRevokedError(payload.jti)

        # 3. 사용자 토큰 저장소 확인
        if not await self._user_token_store.contains(payload.user_id.value, payload.jti):
            raise TokenRevokedError("Refresh token not found in store")

        # 4. 메타데이터 조회 (device_id, user_agent 유지)
        metadata = await self._user_token_store.get_metadata(payload.jti)

        # 5. 사용자 조회
        user = await self._user_query_gateway.get_by_id(UserId(value=payload.user_id.value))
        if not user:
            raise UserNotFoundError(str(payload.user_id.value))

        # 6. 기존 토큰 폐기 (이벤트 발행 - auth_worker가 Redis에 저장)
        await self._user_token_store.remove(payload.user_id.value, payload.jti)
        await self._blacklist_publisher.publish_add(payload, reason="token_rotated")

        # 7. 새 토큰 발급
        token_pair = self._token_service.issue_pair(
            user_id=user.id_.value,
            provider=payload.provider,
        )

        # 8. 새 토큰 저장
        await self._user_token_store.register(
            user_id=user.id_.value,
            jti=token_pair.refresh_jti,
            issued_at=token_pair.access_expires_at - 900,
            expires_at=token_pair.refresh_expires_at,
            device_id=metadata.device_id if metadata else None,
            user_agent=metadata.user_agent if metadata else None,
        )

        await self._transaction_manager.commit()

        logger.info(f"Session refreshed: user_id={user.id_}")

        return RefreshTokensResponse(
            user_id=user.id_.value,
            access_token=token_pair.access_token,
            refresh_token=token_pair.refresh_token,
            access_expires_at=token_pair.access_expires_at,
            refresh_expires_at=token_pair.refresh_expires_at,
        )
