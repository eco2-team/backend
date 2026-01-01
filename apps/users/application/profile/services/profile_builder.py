"""Profile builder service - Constructs UserProfile DTO."""

from __future__ import annotations

from typing import TYPE_CHECKING

from apps.users.application.profile.dto import UserProfile
from apps.users.domain.services import UserService

if TYPE_CHECKING:
    from apps.users.application.identity.ports import SocialAccountInfo
    from apps.users.domain.entities.user import User


class ProfileBuilder:
    """UserProfile DTO를 구성하는 애플리케이션 서비스.

    GetProfileQuery와 UpdateProfileInteractor에서 공통으로 사용됩니다.
    """

    def __init__(self, user_service: UserService) -> None:
        self._user_service = user_service

    def build(
        self,
        user: User,
        accounts: list[SocialAccountInfo],
        current_provider: str,
    ) -> UserProfile:
        """User 엔티티와 소셜 계정 정보로 UserProfile DTO를 생성합니다.

        Args:
            user: User 도메인 엔티티
            accounts: 소셜 계정 정보 목록
            current_provider: 현재 로그인에 사용된 OAuth 프로바이더

        Returns:
            UserProfile DTO
        """
        account = self._select_account(accounts, current_provider)

        display_name = self._user_service.resolve_display_name(user)
        nickname = self._user_service.resolve_nickname(user, display_name)

        return UserProfile(
            display_name=display_name,
            nickname=nickname,
            phone_number=self._user_service.format_phone_for_display(user.phone_number),
            provider=account.provider if account else current_provider,
            last_login_at=account.last_login_at if account else None,
        )

    @staticmethod
    def _select_account(
        accounts: list[SocialAccountInfo],
        current_provider: str,
    ) -> SocialAccountInfo | None:
        """현재 프로바이더에 해당하는 계정을 선택합니다.

        우선순위:
        1. 현재 프로바이더와 일치하는 계정
        2. 가장 최근 로그인한 계정
        """
        if not accounts:
            return None

        # 현재 프로바이더에 해당하는 계정
        for acc in accounts:
            if acc.provider == current_provider:
                return acc

        # Fallback: 가장 최근 활동 계정
        return max(
            accounts,
            key=lambda a: a.last_login_at if a.last_login_at else a.last_login_at,
            default=accounts[0] if accounts else None,
        )
