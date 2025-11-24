from domains._shared.security import build_access_token_dependency

from domains.location.core.config import get_settings

ACCESS_COOKIE_NAME = "s_access"

access_token_dependency = build_access_token_dependency(
    get_settings,
    cookie_alias=ACCESS_COOKIE_NAME,
)

__all__ = ["access_token_dependency"]

