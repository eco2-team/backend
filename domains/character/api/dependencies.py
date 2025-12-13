from __future__ import annotations

from uuid import UUID
from typing import Optional

from fastapi import Header, HTTPException, status
from pydantic import BaseModel

from domains.character.core import get_settings


class UserInfo(BaseModel):
    """ext-authz에서 주입된 사용자 정보"""

    user_id: UUID
    provider: str

    class Config:
        frozen = True


_settings = get_settings()

_DISABLED_USER = UserInfo(
    user_id=UUID("00000000-0000-0000-0000-000000000000"),
    provider="disabled",
)


async def _extract_user_info(
    x_user_id: Optional[str] = Header(default=None, alias="x-user-id"),
    x_auth_provider: Optional[str] = Header(default=None, alias="x-auth-provider"),
) -> UserInfo:
    """ext-authz가 주입한 헤더에서 사용자 정보 추출"""
    if not x_user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing x-user-id header",
        )
    try:
        user_id = UUID(x_user_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid x-user-id format",
        ) from exc

    return UserInfo(user_id=user_id, provider=x_auth_provider or "unknown")


if _settings.auth_disabled:

    async def get_current_user() -> UserInfo:
        """로컬 테스트용 - 인증 우회"""
        return _DISABLED_USER

else:
    get_current_user = _extract_user_info


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


__all__ = ["get_current_user", "service_token_dependency", "UserInfo"]
