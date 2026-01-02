"""Social account gateway port.

소셜 계정 연결 조회 인터페이스입니다.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True, slots=True)
class SocialAccountInfo:
    """소셜 계정 정보 DTO."""

    provider: str
    provider_user_id: str
    email: str | None
    last_login_at: datetime | None


class SocialAccountQueryGateway(Protocol):
    """소셜 계정 조회 포트.

    Note: users.user_social_accounts 테이블을 조회합니다.
    """

    async def list_by_user_id(self, user_id: UUID) -> list[SocialAccountInfo]:
        """사용자의 소셜 계정 목록을 조회합니다."""
        ...

    async def get_by_provider(self, user_id: UUID, provider: str) -> SocialAccountInfo | None:
        """특정 프로바이더의 소셜 계정을 조회합니다."""
        ...
