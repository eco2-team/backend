"""UsersQueryGateway Port.

사용자 읽기 작업을 위한 Gateway 인터페이스입니다.
"""

from typing import Protocol

from apps.auth.domain.entities.user import User
from apps.auth.domain.value_objects.user_id import UserId


class UsersQueryGateway(Protocol):
    """사용자 Query Gateway (읽기 작업).

    구현체:
        - SqlaUsersQueryGateway (infrastructure/persistence_postgres/adapters/)
    """

    async def get_by_id(self, user_id: UserId) -> User | None:
        """ID로 사용자 조회.

        Args:
            user_id: 조회할 사용자 ID

        Returns:
            사용자 엔티티 또는 None
        """
        ...

    async def get_by_provider(self, provider: str, provider_user_id: str) -> User | None:
        """OAuth 프로바이더 정보로 사용자 조회.

        Args:
            provider: OAuth 프로바이더 (google, kakao, naver)
            provider_user_id: 프로바이더에서의 사용자 ID

        Returns:
            사용자 엔티티 또는 None
        """
        ...
