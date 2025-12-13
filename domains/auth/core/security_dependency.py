from typing import Optional
from fastapi import Depends, HTTPException, status, Header
from domains.auth.core.config import get_settings
from domains.auth.core.jwt import TokenPayload, TokenType, decode_jwt
from domains.auth.services.token_blacklist import TokenBlacklist


async def access_token_dependency(
    authorization: Optional[str] = Header(default=None),
    blacklist: TokenBlacklist = Depends(TokenBlacklist),
) -> TokenPayload:
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing authorization header"
        )
    scheme, _, jwt_token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not jwt_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authorization format"
        )

    settings = get_settings()
    payload = decode_jwt(
        jwt_token,
        secret=settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
        audience=settings.jwt_audience,
        issuer=settings.jwt_issuer,
    )

    if payload.type is not TokenType.ACCESS:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token type mismatch")

    if await blacklist.contains(payload.jti):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token revoked")

    return payload
