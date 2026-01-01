"""UserCommandGateway Port.

사용자 쓰기 작업을 위한 Gateway 인터페이스입니다.
"""

from typing import Protocol

from apps.auth.domain.entities.user import User
from apps.auth.domain.value_objects.user_id import UserId


class UserCommandGateway(Protocol):
    """사용자 Command Gateway (쓰기 작업).

    구현체:
        - SqlaUserDataMapper (infrastructure/adapters/)
    """

    def add(self, user: User) -> None:
        """새 사용자 추가.

        Session에 추가만 하고 커밋은 Flusher/TransactionManager에서 처리합니다.

        Args:
            user: 추가할 사용자 엔티티
        """
        ...

    async def update(self, user: User) -> None:
        """사용자 정보 업데이트.

        Args:
            user: 업데이트할 사용자 엔티티
        """
        ...

    async def delete(self, user_id: UserId) -> None:
        """사용자 삭제.

        Args:
            user_id: 삭제할 사용자 ID
        """
        ...
