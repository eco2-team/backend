from typing import Optional
from fastapi import Cookie, Depends, HTTPException, status, Header
from domains.auth.core.config import get_settings
from domains._shared.security.jwt import decode_jwt, TokenType, TokenPayload
from domains.auth.services.key_manager import KeyManager
from domains.auth.services.token_blacklist import TokenBlacklist

ACCESS_COOKIE_NAME = "s_access"


async def access_token_dependency(
    token: Optional[str] = Cookie(default=None, alias=ACCESS_COOKIE_NAME),
    authorization: Optional[str] = Header(default=None),
    blacklist: TokenBlacklist = Depends(TokenBlacklist),
) -> TokenPayload:
    jwt_token = token

    if not jwt_token and authorization:
        scheme, _, value = authorization.partition(" ")
        if scheme.lower() == "bearer":
            jwt_token = value

    if not jwt_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing access token")

    settings = get_settings()
    # Verify signature using Public Key
    payload = decode_jwt(
        jwt_token,
        secret=KeyManager.get_public_key_pem(),
        algorithm="RS256",
        audience=settings.jwt_audience,
        issuer=settings.jwt_issuer,
    )

    if payload.type is not TokenType.ACCESS:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token type mismatch")

    if await blacklist.contains(payload.jti):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token revoked")

    return payload
