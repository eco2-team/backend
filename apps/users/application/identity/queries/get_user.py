"""GetUser query - 사용자 조회 UseCase."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from apps.users.application.profile.ports.profile_gateway import ProfileQueryGateway


@dataclass(frozen=True, slots=True)
class UserResult:
    """사용자 조회 결과 DTO."""

    user_id: UUID
    nickname: str | None
    email: str | None
    phone_number: str | None
    profile_image_url: str | None
    created_at: datetime
    updated_at: datetime
    last_login_at: datetime | None


class GetUserQuery:
    """사용자 조회 UseCase.

    ID로 사용자를 조회합니다.
    """

    def __init__(
        self,
        query_gateway: ProfileQueryGateway,
    ) -> None:
        self._query_gateway = query_gateway

    async def execute(self, user_id: UUID) -> UserResult | None:
        """사용자를 조회합니다.

        Args:
            user_id: 사용자 UUID

        Returns:
            사용자 정보, 없으면 None
        """
        user = await self._query_gateway.get_by_id(user_id)
        if user is None:
            return None

        return UserResult(
            user_id=user.id,
            nickname=user.nickname,
            email=user.email,
            phone_number=user.phone_number,
            profile_image_url=user.profile_image_url,
            created_at=user.created_at,
            updated_at=user.updated_at,
            last_login_at=user.last_login_at,
        )
