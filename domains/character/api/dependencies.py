from __future__ import annotations

from fastapi import Header, HTTPException, status

from domains._shared.security import TokenPayload, TokenType, build_access_token_dependency
from domains.character.core import get_settings

_settings = get_settings()

_DISABLED_TOKEN = TokenPayload(
    sub="00000000-0000-0000-0000-000000000000",
    jti="character-auth-disabled",
    type=TokenType.ACCESS,
    exp=4102444800,
    iat=0,
    provider="disabled",
)

if _settings.auth_disabled:

    async def access_token_dependency() -> TokenPayload:
        return _DISABLED_TOKEN

else:
    access_token_dependency = build_access_token_dependency(
        get_settings,
    )


async def service_token_dependency(
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> None:
    """
    Validate that the caller is an internal service by checking a shared secret header.
    Accepts Authorization: Bearer <CHARACTER_SERVICE_TOKEN_SECRET>.
    """

    secret = _settings.service_token_secret
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service token secret is not configured",
        )

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing service authorization header",
        )

    token = authorization.removeprefix("Bearer ").strip()
    if token != secret:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid service authorization token",
        )


__all__ = ["access_token_dependency", "service_token_dependency"]
