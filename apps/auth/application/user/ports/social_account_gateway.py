"""SocialAccountGateway Port.

소셜 계정 관련 Gateway 인터페이스입니다.
"""

from typing import Protocol

from apps.auth.domain.entities.user_social_account import UserSocialAccount


class SocialAccountGateway(Protocol):
    """소셜 계정 Gateway.

    구현체:
        - SqlaSocialAccountMapper (infrastructure/adapters/)
    """

    def add(self, social_account: UserSocialAccount) -> None:
        """새 소셜 계정 추가.

        Args:
            social_account: 추가할 소셜 계정 엔티티
        """
        ...

    async def update(self, social_account: UserSocialAccount) -> None:
        """소셜 계정 정보 업데이트.

        Args:
            social_account: 업데이트할 소셜 계정 엔티티
        """
        ...

    async def get_by_provider(
        self, provider: str, provider_user_id: str
    ) -> UserSocialAccount | None:
        """프로바이더 정보로 소셜 계정 조회.

        Args:
            provider: OAuth 프로바이더
            provider_user_id: 프로바이더에서의 사용자 ID

        Returns:
            소셜 계정 엔티티 또는 None
        """
        ...
