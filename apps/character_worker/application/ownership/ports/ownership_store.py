"""Ownership Store Port."""

from abc import ABC, abstractmethod
from typing import Sequence

from apps.character_worker.application.ownership.dto import OwnershipEvent


class OwnershipStore(ABC):
    """소유권 저장 포트.

    character.character_ownerships 테이블에 저장합니다.
    """

    @abstractmethod
    async def bulk_insert_ignore(self, events: Sequence[OwnershipEvent]) -> int:
        """여러 소유권을 일괄 저장합니다.

        ON CONFLICT DO NOTHING을 사용하여 중복을 무시합니다.

        Args:
            events: 소유권 이벤트 목록

        Returns:
            실제 삽입된 행 수
        """
        ...
