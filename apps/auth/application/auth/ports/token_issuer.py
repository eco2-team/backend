"""TokenIssuer Port.

JWT 토큰 발급/검증을 위한 Gateway 인터페이스입니다.
"""

from typing import Protocol
from uuid import UUID

from apps.auth.domain.enums.token_type import TokenType
from apps.auth.domain.value_objects.token_payload import TokenPayload


class TokenPair:
    """토큰 쌍 데이터 클래스."""

    __slots__ = (
        "access_token",
        "refresh_token",
        "access_jti",
        "refresh_jti",
        "access_expires_at",
        "refresh_expires_at",
    )

    def __init__(
        self,
        *,
        access_token: str,
        refresh_token: str,
        access_jti: str,
        refresh_jti: str,
        access_expires_at: int,
        refresh_expires_at: int,
    ) -> None:
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.access_jti = access_jti
        self.refresh_jti = refresh_jti
        self.access_expires_at = access_expires_at
        self.refresh_expires_at = refresh_expires_at


class TokenIssuer(Protocol):
    """토큰 발급자 인터페이스.

    구현체:
        - JwtTokenService (infrastructure/security/)
    """

    def issue_pair(self, *, user_id: UUID, provider: str) -> TokenPair:
        """액세스/리프레시 토큰 쌍 발급.

        Args:
            user_id: 사용자 ID
            provider: OAuth 프로바이더

        Returns:
            토큰 쌍
        """
        ...

    def decode(self, token: str) -> TokenPayload:
        """토큰 디코딩 및 검증.

        Args:
            token: JWT 토큰 문자열

        Returns:
            디코딩된 토큰 페이로드

        Raises:
            InvalidTokenError: 유효하지 않은 토큰
            TokenExpiredError: 만료된 토큰
        """
        ...

    def ensure_type(self, payload: TokenPayload, expected_type: TokenType) -> None:
        """토큰 타입 검증.

        Args:
            payload: 토큰 페이로드
            expected_type: 기대하는 토큰 타입

        Raises:
            TokenTypeMismatchError: 타입 불일치
        """
        ...
