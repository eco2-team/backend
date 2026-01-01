"""User profile DTOs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class UserProfile:
    """사용자 프로필 DTO.

    Note:
        - display_name: 화면에 표시할 이름 (nickname → name → fallback)
        - nickname: 서비스 내 닉네임
    """

    display_name: str
    nickname: str
    phone_number: str | None
    provider: str
    last_login_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class UserUpdate:
    """사용자 프로필 업데이트 DTO."""

    nickname: str | None = None
    phone_number: str | None = None

    def has_changes(self) -> bool:
        """변경사항이 있는지 확인합니다."""
        return self.nickname is not None or self.phone_number is not None
