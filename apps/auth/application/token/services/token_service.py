"""TokenService - 토큰 발급 및 세션 관리 서비스.

"연주자" 역할: JWT 토큰 발급 및 세션 등록을 담당합니다.
UseCase(지휘자)가 이 서비스를 호출하여 토큰 관련 작업을 위임합니다.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import UUID

from apps.auth.domain.enums.token_type import TokenType

if TYPE_CHECKING:
    from apps.auth.application.token.ports import (
        TokenBlacklistStore,
        TokenIssuer,
        TokenSessionStore,
    )
    from apps.auth.domain.value_objects.token_payload import TokenPayload

logger = logging.getLogger(__name__)


@dataclass
class TokenIssuanceResult:
    """토큰 발급 결과."""

    access_token: str
    refresh_token: str
    access_jti: str
    refresh_jti: str
    access_expires_at: int
    refresh_expires_at: int


class TokenService:
    """토큰 발급 및 세션 관리 서비스.

    Responsibilities:
        - JWT 토큰 쌍 발급
        - 토큰 세션 등록/관리
        - 토큰 검증 및 디코딩
        - 리프레시 토큰으로 새 토큰 발급

    Collaborators:
        - TokenIssuer: JWT 토큰 발급/검증
        - TokenSessionStore: 토큰 세션 저장/조회
        - TokenBlacklistStore: 블랙리스트 관리 (선택)
    """

    def __init__(
        self,
        issuer: "TokenIssuer",
        session_store: "TokenSessionStore",
        blacklist_store: "TokenBlacklistStore | None" = None,
    ) -> None:
        self._issuer = issuer
        self._session_store = session_store
        self._blacklist_store = blacklist_store

    async def issue_and_register(
        self,
        *,
        user_id: UUID,
        provider: str,
        device_id: str | None = None,
        user_agent: str | None = None,
    ) -> TokenIssuanceResult:
        """토큰을 발급하고 세션에 등록합니다.

        Args:
            user_id: 사용자 ID
            provider: OAuth 프로바이더
            device_id: 기기 ID (선택)
            user_agent: User-Agent (선택)

        Returns:
            TokenIssuanceResult: 발급된 토큰 정보
        """
        # 1. 토큰 쌍 발급
        token_pair = self._issuer.issue_pair(user_id=user_id, provider=provider)

        # 2. 세션 등록 (리프레시 토큰 기준)
        # issued_at은 현재 시간 사용 (토큰 발급 직후이므로 정확함)
        issued_at = int(time.time())

        await self._session_store.register(
            user_id=user_id,
            jti=token_pair.refresh_jti,
            issued_at=issued_at,
            expires_at=token_pair.refresh_expires_at,
            device_id=device_id,
            user_agent=user_agent,
        )

        logger.info(
            "Token issued and session registered",
            extra={
                "user_id": str(user_id),
                "access_jti": token_pair.access_jti,
                "refresh_jti": token_pair.refresh_jti,
            },
        )

        return TokenIssuanceResult(
            access_token=token_pair.access_token,
            refresh_token=token_pair.refresh_token,
            access_jti=token_pair.access_jti,
            refresh_jti=token_pair.refresh_jti,
            access_expires_at=token_pair.access_expires_at,
            refresh_expires_at=token_pair.refresh_expires_at,
        )

    def decode_and_validate(
        self,
        token: str,
        expected_type: TokenType | None = None,
    ) -> "TokenPayload":
        """토큰을 디코딩하고 검증합니다.

        Args:
            token: JWT 토큰
            expected_type: 기대하는 토큰 타입 (선택)

        Returns:
            TokenPayload: 디코딩된 페이로드

        Raises:
            InvalidTokenError: 유효하지 않은 토큰
            TokenExpiredError: 만료된 토큰
            TokenTypeMismatchError: 타입 불일치
        """
        payload = self._issuer.decode(token)

        if expected_type is not None:
            self._issuer.ensure_type(payload, expected_type)

        return payload

    async def validate_session(self, user_id: UUID, jti: str) -> bool:
        """토큰 세션이 유효한지 확인합니다.

        Args:
            user_id: 사용자 ID
            jti: JWT Token ID

        Returns:
            유효하면 True
        """
        return await self._session_store.contains(user_id, jti)

    async def revoke_session(self, user_id: UUID, jti: str) -> None:
        """토큰 세션을 취소합니다.

        Args:
            user_id: 사용자 ID
            jti: JWT Token ID
        """
        await self._session_store.remove(user_id, jti)
        logger.info(
            "Token session revoked",
            extra={"user_id": str(user_id), "jti": jti},
        )

    async def is_blacklisted(self, jti: str) -> bool:
        """토큰이 블랙리스트에 있는지 확인합니다.

        Args:
            jti: JWT Token ID

        Returns:
            블랙리스트에 있으면 True
        """
        if self._blacklist_store is None:
            return False
        return await self._blacklist_store.contains(jti)

    async def refresh_tokens(
        self,
        *,
        user_id: UUID,
        old_refresh_jti: str,
        provider: str,
        device_id: str | None = None,
        user_agent: str | None = None,
    ) -> TokenIssuanceResult:
        """기존 리프레시 토큰을 폐기하고 새 토큰을 발급합니다.

        Args:
            user_id: 사용자 ID
            old_refresh_jti: 기존 리프레시 토큰 JTI
            provider: OAuth 프로바이더
            device_id: 기기 ID (선택)
            user_agent: User-Agent (선택)

        Returns:
            새로 발급된 토큰 정보
        """
        # 1. 기존 세션 폐기
        await self._session_store.remove(user_id, old_refresh_jti)

        # 2. 새 토큰 발급 및 등록
        return await self.issue_and_register(
            user_id=user_id,
            provider=provider,
            device_id=device_id,
            user_agent=user_agent,
        )
