from domains._shared.security import TokenPayload, TokenType, build_access_token_dependency

from domains.location.core.config import get_settings

ACCESS_COOKIE_NAME = "s_access"

_DISABLED_TOKEN = TokenPayload(
    sub="00000000-0000-0000-0000-000000000000",
    jti="location-auth-disabled",
    type=TokenType.ACCESS,
    exp=4102444800,  # 2100-01-01 UTC
    iat=0,
    provider="disabled",
)

if get_settings().auth_disabled:

    async def access_token_dependency() -> TokenPayload:
        """
        Bypass authentication entirely for local/manual testing.
        """

        return _DISABLED_TOKEN

else:
    access_token_dependency = build_access_token_dependency(
        get_settings,
    )

__all__ = ["access_token_dependency"]
