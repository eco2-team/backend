"""Character Client Port - Character API 호출 추상화.

순수 API 호출만 담당.
비즈니스 로직(컨텍스트 변환)은 CharacterService에서 수행.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class CharacterDTO:
    """캐릭터 정보 DTO.

    Application Layer에서 사용하는 불변 데이터 객체.
    """

    name: str
    type_label: str
    dialog: str
    match_label: str | None


class CharacterClientPort(ABC):
    """Character API 클라이언트 Port.

    순수 API 호출만 담당.
    Infrastructure Layer에서 구현 (gRPC 또는 HTTP).
    """

    @abstractmethod
    async def get_character_by_waste_category(
        self,
        waste_category: str,
    ) -> CharacterDTO | None:
        """폐기물 카테고리로 캐릭터 조회."""
        pass

    @abstractmethod
    async def get_catalog(self) -> list[CharacterDTO]:
        """전체 카탈로그 조회."""
        pass
