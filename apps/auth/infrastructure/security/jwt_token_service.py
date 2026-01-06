"""JWT Token Service.

TokenService 포트의 구현체입니다.
"""

from __future__ import annotations

import time
import uuid
from datetime import timedelta
from typing import Any

from jose import JWTError, jwt

from apps.auth.application.token.ports import TokenPair
from apps.auth.domain.enums.token_type import TokenType
from apps.auth.domain.exceptions.auth import (
    InvalidTokenError,
    TokenExpiredError,
    TokenTypeMismatchError,
)
from apps.auth.domain.value_objects.token_payload import TokenPayload
from apps.auth.domain.value_objects.user_id import UserId


class JwtTokenService:
    """JWT 토큰 서비스.

    TokenService 구현체.
    """

    def __init__(
        self,
        *,
        secret_key: str,
        algorithm: str = "HS256",
        issuer: str = "auth-service",
        audience: str = "eco2-api",
        access_token_expire_minutes: int = 15,
        refresh_token_expire_minutes: int = 10080,  # 7일
    ) -> None:
        self._secret_key = secret_key
        self._algorithm = algorithm
        self._issuer = issuer
        self._audience = audience
        self._access_token_expire = timedelta(minutes=access_token_expire_minutes)
        self._refresh_token_expire = timedelta(minutes=refresh_token_expire_minutes)

    def _now_timestamp(self) -> int:
        """현재 UTC Unix timestamp 반환."""
        return int(time.time())

    def _create_token(
        self,
        *,
        user_id: uuid.UUID,
        provider: str,
        token_type: TokenType,
        expires_delta: timedelta,
    ) -> tuple[str, str, int]:
        """토큰 생성."""
        jti = str(uuid.uuid4())
        now = self._now_timestamp()
        expires_at = now + int(expires_delta.total_seconds())

        payload: dict[str, Any] = {
            "sub": str(user_id),
            "jti": jti,
            "type": token_type.value,
            "exp": expires_at,
            "iat": now,
            "nbf": now,
            "iss": self._issuer,
            "aud": self._audience,
            "provider": provider,
        }

        token = jwt.encode(payload, self._secret_key, algorithm=self._algorithm)
        return token, jti, expires_at

    def issue_pair(self, *, user_id: uuid.UUID, provider: str) -> TokenPair:
        """토큰 쌍 발급."""
        access_token, access_jti, access_exp = self._create_token(
            user_id=user_id,
            provider=provider,
            token_type=TokenType.ACCESS,
            expires_delta=self._access_token_expire,
        )
        refresh_token, refresh_jti, refresh_exp = self._create_token(
            user_id=user_id,
            provider=provider,
            token_type=TokenType.REFRESH,
            expires_delta=self._refresh_token_expire,
        )
        return TokenPair(
            access_token=access_token,
            refresh_token=refresh_token,
            access_jti=access_jti,
            refresh_jti=refresh_jti,
            access_expires_at=access_exp,
            refresh_expires_at=refresh_exp,
        )

    def decode(self, token: str) -> TokenPayload:
        """토큰 디코딩."""
        try:
            payload = jwt.decode(
                token,
                self._secret_key,
                algorithms=[self._algorithm],
                audience=self._audience,
                issuer=self._issuer,
            )
            return TokenPayload(
                user_id=UserId.from_string(payload["sub"]),
                jti=payload["jti"],
                token_type=TokenType(payload["type"]),
                exp=payload["exp"],
                iat=payload["iat"],
                provider=payload["provider"],
            )
        except JWTError as e:
            if "expired" in str(e).lower():
                raise TokenExpiredError() from e
            raise InvalidTokenError(str(e)) from e

    def ensure_type(self, payload: TokenPayload, expected_type: TokenType) -> None:
        """토큰 타입 검증."""
        if payload.token_type != expected_type:
            raise TokenTypeMismatchError(
                expected=expected_type.value,
                actual=payload.token_type.value,
            )
