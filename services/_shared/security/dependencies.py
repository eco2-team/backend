from typing import Annotated, Callable, Optional

from fastapi import Cookie, Depends, HTTPException, status

from services._shared.security.jwt import TokenPayload, TokenType, decode_jwt


def build_access_token_dependency(
    get_settings: Callable,
    *,
    cookie_alias: str = "s_access",
) -> Callable:
    async def dependency(
        token: Annotated[Optional[str], Cookie(alias=cookie_alias)] = None,
        settings=Depends(get_settings),
    ) -> TokenPayload:
        if not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing access token"
            )

        payload = decode_jwt(
            token,
            secret=settings.jwt_secret_key,
            algorithm=settings.jwt_algorithm,
            audience=settings.jwt_audience,
            issuer=settings.jwt_issuer,
        )

        if payload.type != TokenType.ACCESS:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Token type mismatch"
            )

        return payload

    return dependency
