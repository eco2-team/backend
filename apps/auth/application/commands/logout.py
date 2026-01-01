"""Logout Command.

로그아웃 Use Case입니다.
"""

from __future__ import annotations

import logging

from apps.auth.domain.enums.token_type import TokenType
from apps.auth.application.common.dto.auth import LogoutRequest
from apps.auth.application.common.ports.token_service import TokenService
from apps.auth.application.common.ports.blacklist_event_publisher import (
    BlacklistEventPublisher,
)
from apps.auth.application.common.ports.user_token_store import UserTokenStore
from apps.auth.application.common.ports.transaction_manager import TransactionManager

logger = logging.getLogger(__name__)


class LogoutInteractor:
    """로그아웃 Interactor.

    로그아웃 플로우:
    1. Access 토큰 블랙리스트 이벤트 발행
    2. Refresh 토큰 블랙리스트 이벤트 발행
    3. 사용자 토큰 저장소에서 제거

    Note:
        Redis 직접 저장 대신 이벤트를 발행합니다.
        auth_worker가 이벤트를 소비하여 Redis에 저장합니다.
    """

    def __init__(
        self,
        token_service: TokenService,
        blacklist_publisher: BlacklistEventPublisher,
        user_token_store: UserTokenStore,
        transaction_manager: TransactionManager,
    ) -> None:
        self._token_service = token_service
        self._blacklist_publisher = blacklist_publisher
        self._user_token_store = user_token_store
        self._transaction_manager = transaction_manager

    async def execute(self, request: LogoutRequest) -> None:
        """로그아웃 처리.

        Args:
            request: 로그아웃 요청 DTO

        Note:
            토큰이 유효하지 않아도 예외를 발생시키지 않습니다.
            클라이언트 쿠키 삭제는 Presentation 레이어에서 처리합니다.
        """
        # 1. Access 토큰 처리
        if request.access_token:
            try:
                payload = self._token_service.decode(request.access_token)
                self._token_service.ensure_type(payload, TokenType.ACCESS)
                await self._blacklist_publisher.publish_add(payload, reason="logout")
            except Exception:
                # 토큰이 유효하지 않아도 무시
                pass

        # 2. Refresh 토큰 처리
        if request.refresh_token:
            try:
                payload = self._token_service.decode(request.refresh_token)
                self._token_service.ensure_type(payload, TokenType.REFRESH)
                await self._blacklist_publisher.publish_add(payload, reason="logout")
                await self._user_token_store.remove(payload.user_id.value, payload.jti)
            except Exception:
                # 토큰이 유효하지 않아도 무시
                pass

        await self._transaction_manager.commit()
        logger.info("User logged out")
