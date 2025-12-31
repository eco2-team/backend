"""Get characters query - Retrieves user's character inventory."""

from __future__ import annotations

import logging
from uuid import UUID

from apps.users.application.common.dto import CharacterOwnership, UserCharacterDTO
from apps.users.application.common.ports import UserCharacterQueryGateway

logger = logging.getLogger(__name__)


class GetCharactersQuery:
    """사용자 캐릭터 목록 조회 쿼리."""

    def __init__(
        self,
        character_gateway: UserCharacterQueryGateway,
    ) -> None:
        self._character_gateway = character_gateway

    async def execute(self, user_id: UUID) -> list[UserCharacterDTO]:
        """사용자의 캐릭터 목록을 조회합니다.

        Args:
            user_id: 사용자 ID (auth.users.id)

        Returns:
            캐릭터 목록
        """
        logger.info("Characters fetched", extra={"user_id": str(user_id)})

        characters = await self._character_gateway.list_by_user_id(user_id)

        return [
            UserCharacterDTO(
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
            for char in characters
        ]


class CheckCharacterOwnershipQuery:
    """캐릭터 소유 여부 확인 쿼리."""

    def __init__(
        self,
        character_gateway: UserCharacterQueryGateway,
    ) -> None:
        self._character_gateway = character_gateway

    async def execute(self, user_id: UUID, character_code: str) -> CharacterOwnership:
        """특정 캐릭터의 소유 여부를 확인합니다.

        Args:
            user_id: 사용자 ID
            character_code: 캐릭터 코드

        Returns:
            소유 여부 정보
        """
        logger.info(
            "Character ownership checked",
            extra={"user_id": str(user_id), "character_code": character_code},
        )

        character = await self._character_gateway.get_by_character_code(
            user_id, character_code
        )

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
