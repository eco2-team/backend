"""Character Service - 캐릭터 비즈니스 로직.

Character API 호출 및 컨텍스트 변환을 담당.

Clean Architecture:
- Service: 비즈니스 로직 (이 파일)
- Port: CharacterClientPort (API 호출만)
- DTO: CharacterDTO
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from chat_worker.application.integrations.character.ports import (
        CharacterClientPort,
        CharacterDTO,
    )

logger = logging.getLogger(__name__)


class CharacterService:
    """캐릭터 비즈니스 로직 서비스.

    책임:
    - 캐릭터 검색 (Port 호출)
    - 컨텍스트 변환 (to_answer_context)
    """

    def __init__(self, client: "CharacterClientPort"):
        self._client = client

    async def find_by_waste_category(
        self,
        waste_category: str,
    ) -> "CharacterDTO | None":
        """폐기물 카테고리로 캐릭터 검색."""
        character = await self._client.get_character_by_waste_category(waste_category)

        if character:
            logger.info(
                "Character found",
                extra={
                    "waste_category": waste_category,
                    "character_name": character.name,
                },
            )
        else:
            logger.info(
                "No character found",
                extra={"waste_category": waste_category},
            )

        return character

    async def get_all(self) -> list["CharacterDTO"]:
        """전체 캐릭터 목록 조회."""
        return await self._client.get_catalog()

    @staticmethod
    def to_answer_context(character: "CharacterDTO") -> dict[str, Any]:
        """Answer 노드용 컨텍스트 생성."""
        return {
            "name": character.name,
            "type": character.type_label,
            "dialog": character.dialog,
            "match_reason": character.match_label,
        }
