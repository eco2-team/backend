"""Ownership Checker Port."""

from abc import ABC, abstractmethod
from uuid import UUID


class OwnershipChecker(ABC):
    """캐릭터 소유권 확인 포트."""

    @abstractmethod
    async def is_owned(self, user_id: UUID, character_id: UUID) -> bool:
        """사용자가 캐릭터를 소유하고 있는지 확인합니다.

        Args:
            user_id: 사용자 ID
            character_id: 캐릭터 ID

        Returns:
            소유 여부
        """
        ...
