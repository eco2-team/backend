from __future__ import annotations

from uuid import UUID
from typing import Optional

from fastapi import Header, HTTPException, status
from pydantic import BaseModel

from domains.image.core.config import get_settings


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


__all__ = ["get_current_user", "UserInfo"]
