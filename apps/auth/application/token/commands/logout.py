"""Logout Command.

로그아웃 Use Case입니다.

Architecture:
    - UseCase(지휘자): LogoutInteractor
    - Services(연주자): TokenService
    - Ports(인프라): BlacklistEventPublisher, TransactionManager
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from apps.auth.application.token.dto import LogoutRequest
from apps.auth.domain.enums.token_type import TokenType

if TYPE_CHECKING:
    # Services (연주자)
    # Ports (인프라)
    from apps.auth.application.common.ports import TransactionManager
    from apps.auth.application.token.ports import BlacklistEventPublisher
    from apps.auth.application.token.services import TokenService

logger = logging.getLogger(__name__)


class LogoutInteractor:
    """로그아웃 Interactor (지휘자).

    로그아웃 플로우를 오케스트레이션합니다.

    Workflow:
        1. Access 토큰 블랙리스트 이벤트 발행
        2. Refresh 토큰 블랙리스트 이벤트 발행
        3. 세션 저장소에서 제거 (TokenService)
        4. 트랜잭션 커밋

    Dependencies:
        Services (연주자):
            - token_service: 토큰 검증, 세션 폐기

        Ports (인프라):
            - blacklist_publisher: 블랙리스트 이벤트 발행
            - transaction_manager: 트랜잭션 제어

    Note:
        Redis 직접 저장 대신 이벤트를 발행합니다.
        auth_worker가 이벤트를 소비하여 Redis에 저장합니다.
    """

    def __init__(
        self,
        # Services (연주자)
        token_service: "TokenService",
        # Ports (인프라)
        blacklist_publisher: "BlacklistEventPublisher",
        transaction_manager: "TransactionManager",
    ) -> None:
        # Services
        self._token_service = token_service
        # Ports
        self._blacklist_publisher = blacklist_publisher
        self._transaction_manager = transaction_manager

    async def execute(self, request: LogoutRequest) -> None:
        """로그아웃을 처리합니다.

        Args:
            request: 로그아웃 요청 DTO

        Note:
            토큰이 유효하지 않아도 예외를 발생시키지 않습니다.
            클라이언트 쿠키 삭제는 Presentation 레이어에서 처리합니다.
        """
        # 1. Access 토큰 처리
        if request.access_token:
            try:
                payload = self._token_service.decode_and_validate(
                    request.access_token,
                    expected_type=TokenType.ACCESS,
                )
                await self._blacklist_publisher.publish_add(payload, reason="logout")
            except Exception:
                # 토큰이 유효하지 않아도 무시
                pass

        # 2. Refresh 토큰 처리
        if request.refresh_token:
            try:
                payload = self._token_service.decode_and_validate(
                    request.refresh_token,
                    expected_type=TokenType.REFRESH,
                )
                await self._blacklist_publisher.publish_add(payload, reason="logout")
                # 세션 폐기 (Service에 위임)
                await self._token_service.revoke_session(
                    payload.user_id.value,
                    payload.jti,
                )
            except Exception:
                # 토큰이 유효하지 않아도 무시
                pass

        await self._transaction_manager.commit()
        logger.info("User logged out")
