from __future__ import annotations

import uuid
from datetime import timedelta

from fastapi import Depends, HTTPException, status
from jose import jwt
from pydantic import BaseModel

from domains.auth.setup.config import Settings, get_settings
from domains.auth.infrastructure.auth.security import now_utc, to_unix_timestamp
from domains.auth.infrastructure.auth.jwt import TokenPayload, TokenType, decode_jwt


class TokenPairInternal(BaseModel):
    access_token: str
    refresh_token: str
    access_jti: str
    refresh_jti: str
    access_expires_at: int
    refresh_expires_at: int


class TokenService:
    def __init__(self, settings: Settings = Depends(get_settings)):
        self.settings = settings

    def _create_token(
        self,
        *,
        user_id: uuid.UUID,
        provider: str,
        token_type: TokenType,
        expires_delta: timedelta,
    ) -> tuple[str, str, int]:
        jti = str(uuid.uuid7()) if hasattr(uuid, "uuid7") else str(uuid.uuid4())
        now = now_utc()
        expires_at = now + expires_delta
        payload = {
            "sub": str(user_id),
            "jti": jti,
            "type": token_type.value,
            "exp": to_unix_timestamp(expires_at),
            "iat": to_unix_timestamp(now),
            "nbf": to_unix_timestamp(now),
            "iss": self.settings.jwt_issuer,
            "aud": self.settings.jwt_audience,
            "provider": provider,
        }

        # HS256 서명 (공유 시크릿)
        token = jwt.encode(
            payload, self.settings.jwt_secret_key, algorithm=self.settings.jwt_algorithm
        )
        return token, jti, payload["exp"]

    def issue_pair(self, *, user_id: uuid.UUID, provider: str) -> TokenPairInternal:
        access_token, access_jti, access_exp = self._create_token(
            user_id=user_id,
            provider=provider,
            token_type=TokenType.ACCESS,
            expires_delta=timedelta(minutes=self.settings.access_token_exp_minutes),
        )
        refresh_token, refresh_jti, refresh_exp = self._create_token(
            user_id=user_id,
            provider=provider,
            token_type=TokenType.REFRESH,
            expires_delta=timedelta(minutes=self.settings.refresh_token_exp_minutes),
        )
        return TokenPairInternal(
            access_token=access_token,
            refresh_token=refresh_token,
            access_jti=access_jti,
            refresh_jti=refresh_jti,
            access_expires_at=access_exp,
            refresh_expires_at=refresh_exp,
        )

    def decode(self, token: str) -> TokenPayload:
        return decode_jwt(
            token,
            secret=self.settings.jwt_secret_key,
            algorithm=self.settings.jwt_algorithm,
            audience=self.settings.jwt_audience,
            issuer=self.settings.jwt_issuer,
        )

    def ensure_type(self, payload: TokenPayload, token_type: TokenType) -> TokenPayload:
        if payload.type != token_type:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Token type mismatch"
            )
        return payload
