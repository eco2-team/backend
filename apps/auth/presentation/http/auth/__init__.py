"""Auth HTTP Components.

쿠키 관리, 의존성, 미들웨어를 담당합니다.
"""

from apps.auth.presentation.http.auth.cookie_params import (
    ACCESS_COOKIE_NAME,
    REFRESH_COOKIE_NAME,
    clear_auth_cookies,
    get_cookie_params,
    set_auth_cookies,
)
from apps.auth.presentation.http.auth.dependencies import (
    get_current_user,
    get_optional_user,
)

__all__ = [
    "ACCESS_COOKIE_NAME",
    "REFRESH_COOKIE_NAME",
    "get_cookie_params",
    "set_auth_cookies",
    "clear_auth_cookies",
    "get_current_user",
    "get_optional_user",
]
