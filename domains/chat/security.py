from __future__ import annotations

from domains._shared.security import (
    TokenPayload,
    TokenType,
    build_access_token_dependency,
)
from domains.chat.core.config import get_settings

_settings = get_settings()

_DISABLED_TOKEN = TokenPayload(
    sub="00000000-0000-0000-0000-000000000000",
    jti="chat-auth-disabled",
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

__all__ = ["access_token_dependency"]
