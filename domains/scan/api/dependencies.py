"""Dependency injection for Scan API.

Annotated 타입을 활용한 의존성 주입으로 테스트 용이성 확보.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, HTTPException, status
from pydantic import BaseModel, ConfigDict

from domains.scan.core.config import Settings, get_settings
from domains.scan.services.scan import ScanService


class UserInfo(BaseModel):
    """ext-authz에서 주입된 사용자 정보."""

    user_id: UUID
    provider: str

    model_config = ConfigDict(frozen=True)


_DISABLED_USER = UserInfo(
    user_id=UUID("00000000-0000-0000-0000-000000000000"),
    provider="disabled",
)


async def _extract_user_info(
    x_user_id: str | None = Header(default=None, alias="x-user-id"),
    x_auth_provider: str | None = Header(default=None, alias="x-auth-provider"),
) -> UserInfo:
    """ext-authz가 주입한 헤더에서 사용자 정보 추출."""
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


def _get_current_user_factory():
    """Settings 기반 get_current_user 함수 생성."""
    settings = get_settings()

    if settings.auth_disabled:

        async def get_current_user() -> UserInfo:
            """로컬 테스트용 - 인증 우회."""
            return _DISABLED_USER

        return get_current_user

    return _extract_user_info


get_current_user = _get_current_user_factory()


# ─────────────────────────────────────────────────────────────────────────────
# Annotated Type Aliases (FastAPI DI Pattern)
# ─────────────────────────────────────────────────────────────────────────────

# Settings 의존성
SettingsDep = Annotated[Settings, Depends(get_settings)]

# 현재 사용자 의존성
CurrentUser = Annotated[UserInfo, Depends(get_current_user)]

# ScanService 의존성
ScanServiceDep = Annotated[ScanService, Depends()]


__all__ = [
    "CurrentUser",
    "ScanServiceDep",
    "SettingsDep",
    "UserInfo",
    "get_current_user",
]
