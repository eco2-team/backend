"""Catalog Reader Port."""

from abc import ABC, abstractmethod
from typing import Sequence

from apps.character.domain.entities import Character


class CatalogReader(ABC):
    """캐릭터 카탈로그 조회 포트.

    인프라스트럭처 계층에서 구현됩니다.
    """

    @abstractmethod
    async def list_all(self) -> Sequence[Character]:
        """모든 캐릭터 목록을 조회합니다.

        Returns:
            캐릭터 목록
        """
        ...
