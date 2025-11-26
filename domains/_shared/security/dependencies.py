from __future__ import annotations

from typing import Callable, Optional

from fastapi import Cookie, Depends, HTTPException, status

from .jwt import TokenPayload, TokenType, decode_jwt


def build_access_token_dependency(
    get_settings: Callable,
    *,
    cookie_alias: str = "s_access",
    blacklist_dependency: Optional[type] = None,
):
    """
    Factory that returns a FastAPI dependency for validating access-token cookies.
    """

    if blacklist_dependency is not None:

        async def dependency(
            token: Optional[str] = Cookie(default=None, alias=cookie_alias),
            blacklist=Depends(blacklist_dependency),
        ) -> TokenPayload:
            if not token:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing access token"
                )
            settings = get_settings()
            payload = decode_jwt(
                token,
                secret=settings.jwt_secret_key,
                algorithm=settings.jwt_algorithm,
                audience=settings.jwt_audience,
                issuer=settings.jwt_issuer,
            )
            if payload.type is not TokenType.ACCESS:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED, detail="Token type mismatch"
                )
            if await blacklist.contains(payload.jti):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED, detail="Token revoked"
                )
            return payload

        return dependency

    async def dependency(
        token: Optional[str] = Cookie(default=None, alias=cookie_alias),
    ) -> TokenPayload:
        if not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing access token"
            )
        settings = get_settings()
        payload = decode_jwt(
            token,
            secret=settings.jwt_secret_key,
            algorithm=settings.jwt_algorithm,
            audience=settings.jwt_audience,
            issuer=settings.jwt_issuer,
        )
        if payload.type is not TokenType.ACCESS:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Token type mismatch"
            )
        return payload

    return dependency
