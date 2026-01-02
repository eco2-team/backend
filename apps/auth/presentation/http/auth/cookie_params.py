"""Cookie Parameters.

인증 쿠키 설정을 관리합니다.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import Response

# Cookie names (프론트엔드와 일치해야 함)
ACCESS_COOKIE_NAME = "s_access"
REFRESH_COOKIE_NAME = "s_refresh"

# Cookie settings
COOKIE_PATH = "/"
COOKIE_SAMESITE = "lax"


def get_cookie_params() -> dict:
    """쿠키 공통 파라미터."""
    params = {
        "path": COOKIE_PATH,
        "httponly": True,
        "secure": True,
        "samesite": COOKIE_SAMESITE,
    }
    cookie_domain = os.getenv("AUTH_COOKIE_DOMAIN")
    if cookie_domain:
        params["domain"] = cookie_domain
    return params


def set_auth_cookies(
    response: "Response",
    *,
    access_token: str,
    refresh_token: str,
    access_expires_at: int,
    refresh_expires_at: int,
) -> None:
    """인증 쿠키 설정."""
    import time

    base_params = get_cookie_params()

    # Access token cookie
    access_max_age = max(access_expires_at - int(time.time()), 1)
    response.set_cookie(
        key=ACCESS_COOKIE_NAME,
        value=access_token,
        max_age=access_max_age,
        **base_params,
    )

    # Refresh token cookie
    refresh_max_age = max(refresh_expires_at - int(time.time()), 1)
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=refresh_token,
        max_age=refresh_max_age,
        **base_params,
    )


def clear_auth_cookies(response: "Response") -> None:
    """인증 쿠키 삭제."""
    base_params = get_cookie_params()
    # httponly는 delete_cookie에서 지원 안 함
    del base_params["httponly"]

    response.delete_cookie(ACCESS_COOKIE_NAME, **base_params)
    response.delete_cookie(REFRESH_COOKIE_NAME, **base_params)
