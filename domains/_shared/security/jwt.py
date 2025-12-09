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
    sub: str
    jti: str
    type: TokenType
    exp: int
    iat: int
    provider: str

    @property
    def user_id(self) -> UUID:
        return UUID(self.sub)


def extract_token_payload(token: str) -> TokenPayload:
    """
    Decode JWT payload without signature verification.
    Use this ONLY when the token is already verified by an external entity (e.g., Istio).
    """
    try:
        payload = jwt.get_unverified_claims(token)
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
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Malformed token"
        ) from exc
