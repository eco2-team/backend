"""UsersManagementGateway Port.

users 도메인과의 통신을 추상화하는 포트입니다.
gRPC, HTTP 등 다양한 어댑터로 구현할 수 있습니다.

참고: https://rooftopsnow.tistory.com/127
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True)
class OAuthUserResult:
    """OAuth 사용자 조회/생성 결과."""

    user_id: UUID
    nickname: str | None
    profile_image_url: str | None
    is_new_user: bool


class UsersManagementGateway(Protocol):
    """사용자 관리 Gateway 포트.

    users 도메인의 사용자 관련 기능을 호출하는 인터페이스입니다.
    """

    async def get_or_create_from_oauth(
        self,
        *,
        provider: str,
        provider_user_id: str,
        email: str | None = None,
        nickname: str | None = None,
        profile_image_url: str | None = None,
    ) -> OAuthUserResult | None:
        """OAuth 프로필로 사용자 조회 또는 생성.

        Args:
            provider: OAuth 프로바이더
            provider_user_id: 프로바이더 사용자 ID
            email: 이메일 (선택)
            nickname: 닉네임 (선택)
            profile_image_url: 프로필 이미지 (선택)

        Returns:
            OAuthUserResult or None on failure
        """
        ...

    async def update_login_time(
        self,
        *,
        user_id: UUID,
        provider: str,
        provider_user_id: str,
    ) -> bool:
        """로그인 시간 업데이트.

        Args:
            user_id: 사용자 ID
            provider: OAuth 프로바이더
            provider_user_id: 프로바이더 사용자 ID

        Returns:
            성공 여부
        """
        ...
