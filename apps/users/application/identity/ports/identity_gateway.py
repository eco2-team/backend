"""Identity gateway ports.

OAuth 로그인 관련 사용자 및 소셜 계정 CRUD 인터페이스입니다.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Protocol
from uuid import UUID

if TYPE_CHECKING:
    from apps.users.domain.entities.user import User
    from apps.users.infrastructure.persistence_postgres.mappings.user_social_account import (
        UserSocialAccount,
    )


@dataclass(frozen=True, slots=True)
class UserWithSocialAccount:
    """사용자 + 소셜 계정 정보 DTO."""

    user: "User"
    social_account: "UserSocialAccount"


class IdentityQueryGateway(Protocol):
    """OAuth 식별 조회 포트.

    provider + provider_user_id로 사용자를 조회합니다.
    """

    async def get_by_provider_identity(
        self,
        provider: str,
        provider_user_id: str,
    ) -> UserWithSocialAccount | None:
        """프로바이더 식별자로 사용자를 조회합니다."""
        ...


class IdentityCommandGateway(Protocol):
    """OAuth 식별 수정 포트.

    사용자 및 소셜 계정을 생성/업데이트합니다.
    """

    async def create_user_with_social_account(
        self,
        user_id: UUID,
        provider: str,
        provider_user_id: str,
        email: str | None = None,
        nickname: str | None = None,
        profile_image_url: str | None = None,
    ) -> UserWithSocialAccount:
        """사용자와 소셜 계정을 함께 생성합니다."""
        ...

    async def update_social_login_time(
        self,
        user_id: UUID,
        provider: str,
        provider_user_id: str,
        login_time: datetime,
    ) -> None:
        """소셜 계정과 사용자의 로그인 시간을 업데이트합니다."""
        ...
