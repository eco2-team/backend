from __future__ import annotations

from enum import Enum
from uuid import UUID

from fastapi import HTTPException, status
from jose import JWTError, jwt
from pydantic import BaseModel


class TokenType(str, Enum):
    ACCESS = "access"
    REFRESH = "refresh"


class TokenPayload(BaseModel):
    """JWT 토큰 페이로드 - Auth 도메인 전용"""

    sub: str
    jti: str
    type: TokenType
    exp: int
    iat: int
    provider: str

    @property
    def user_id(self) -> UUID:
        return UUID(self.sub)


def decode_jwt(
    token: str, *, secret: str, algorithm: str, audience: str, issuer: str
) -> TokenPayload:
    """
    Decode and verify JWT signature.
    Use this when internal verification is needed (e.g., Refresh Token Flow in Auth Service).
    """
    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=[algorithm],
            audience=audience,
            issuer=issuer,
        )
        return TokenPayload(
            sub=payload["sub"],
            jti=payload["jti"],
            type=TokenType(payload["type"]),
            exp=payload["exp"],
            iat=payload["iat"],
            provider=payload["provider"],
        )
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token"
        ) from exc
