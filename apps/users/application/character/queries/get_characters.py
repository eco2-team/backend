"""Character Queries.

캐릭터 조회 관련 Query(지휘자)들입니다.

Architecture:
    - Query(지휘자): GetCharactersQuery, CheckCharacterOwnershipQuery
    - Ports(인프라): UserCharacterQueryGateway
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from uuid import UUID

from apps.users.application.character.dto import CharacterOwnership, UserCharacterDTO

if TYPE_CHECKING:
    from apps.users.application.character.ports import UserCharacterQueryGateway
    from apps.users.domain.entities.user_character import UserCharacter

logger = logging.getLogger(__name__)


def _to_character_dto(char: "UserCharacter") -> UserCharacterDTO:
    """도메인 엔티티를 DTO로 변환합니다."""
    return UserCharacterDTO(
        id=char.id,
        character_id=char.character_id,
        character_code=char.character_code,
        character_name=char.character_name,
        character_type=char.character_type,
        character_dialog=char.character_dialog,
        source=char.source,
        status=char.status.value,
        acquired_at=char.acquired_at,
    )


class GetCharactersQuery:
    """사용자 캐릭터 목록 조회 Query (지휘자).

    캐릭터 목록 조회 플로우를 오케스트레이션합니다.

    Workflow:
        1. 캐릭터 목록 조회 (UserCharacterQueryGateway)
        2. DTO 변환

    Dependencies:
        Ports (인프라):
            - character_gateway: 캐릭터 데이터 조회
    """

    def __init__(self, character_gateway: "UserCharacterQueryGateway") -> None:
        self._character_gateway = character_gateway

    async def execute(self, user_id: UUID) -> list[UserCharacterDTO]:
        """사용자의 캐릭터 목록을 조회합니다.

        Args:
            user_id: 사용자 ID

        Returns:
            캐릭터 DTO 목록
        """
        logger.info("Characters query executed", extra={"user_id": str(user_id)})

        # 1. 캐릭터 목록 조회 (Port 직접 호출)
        characters = await self._character_gateway.list_by_user_id(user_id)

        # 2. DTO 변환
        return [_to_character_dto(char) for char in characters]


class CheckCharacterOwnershipQuery:
    """캐릭터 소유 여부 확인 Query (지휘자).

    캐릭터 소유 여부 확인 플로우를 오케스트레이션합니다.

    Workflow:
        1. 캐릭터 소유 정보 조회 (UserCharacterQueryGateway)
        2. 소유 여부 DTO 생성

    Dependencies:
        Ports (인프라):
            - character_gateway: 캐릭터 데이터 조회
    """

    def __init__(self, character_gateway: "UserCharacterQueryGateway") -> None:
        self._character_gateway = character_gateway

    async def execute(self, user_id: UUID, character_code: str) -> CharacterOwnership:
        """특정 캐릭터의 소유 여부를 확인합니다.

        Args:
            user_id: 사용자 ID
            character_code: 캐릭터 코드

        Returns:
            소유 여부 DTO
        """
        logger.info(
            "Character ownership query executed",
            extra={"user_id": str(user_id), "character_code": character_code},
        )

        # 1. 캐릭터 소유 정보 조회 (Port 직접 호출)
        character = await self._character_gateway.get_by_character_code(user_id, character_code)

        # 2. 소유 여부 DTO 생성
        if character is None:
            return CharacterOwnership(
                character_code=character_code,
                owned=False,
            )

        return CharacterOwnership(
            character_code=character_code,
            owned=True,
            acquired_at=character.acquired_at,
        )
