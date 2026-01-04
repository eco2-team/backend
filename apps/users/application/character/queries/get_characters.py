"""Character Queries.

캐릭터 조회 관련 Query(지휘자)들입니다.

Architecture:
    - Query(지휘자): GetCharactersQuery, CheckCharacterOwnershipQuery
    - Ports(인프라): UserCharacterQueryGateway, DefaultCharacterPublisher
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING
from uuid import UUID

from apps.users.application.character.dto import CharacterOwnership, UserCharacterDTO

if TYPE_CHECKING:
    from apps.users.application.character.ports import (
        DefaultCharacterPublisher,
        UserCharacterQueryGateway,
    )
    from apps.users.domain.entities.user_character import UserCharacter
    from apps.users.setup.config import Settings

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
        status=char.status,  # 이미 문자열 ("owned", "burned", "traded")
        acquired_at=char.acquired_at,
    )


class GetCharactersQuery:
    """사용자 캐릭터 목록 조회 Query (지휘자).

    캐릭터 목록 조회 플로우를 오케스트레이션합니다.

    Workflow:
        1. 캐릭터 목록 조회 (UserCharacterQueryGateway)
        2. 빈 목록이면 기본 캐릭터(이코) 반환 + 이벤트 발행 (Eventual Consistency)
        3. DTO 변환

    Dependencies:
        Ports (인프라):
            - character_gateway: 캐릭터 데이터 조회
            - default_publisher: 기본 캐릭터 지급 이벤트 발행 (옵션)
        Config:
            - settings: 기본 캐릭터 응답 설정
    """

    def __init__(
        self,
        character_gateway: "UserCharacterQueryGateway",
        default_publisher: "DefaultCharacterPublisher | None" = None,
        settings: "Settings | None" = None,
    ) -> None:
        self._character_gateway = character_gateway
        self._default_publisher = default_publisher
        self._settings = settings

    async def execute(self, user_id: UUID) -> list[UserCharacterDTO]:
        """사용자의 캐릭터 목록을 조회합니다.

        빈 목록인 경우 기본 캐릭터(이코)를 즉시 반환하고,
        이벤트를 발행하여 character_worker가 DB에 저장하도록 합니다.

        Args:
            user_id: 사용자 ID

        Returns:
            캐릭터 DTO 목록
        """
        logger.info("Characters query executed", extra={"user_id": str(user_id)})

        # 1. 캐릭터 목록 조회 (Port 직접 호출)
        characters = await self._character_gateway.list_by_user_id(user_id)

        # 2. 빈 목록이면 기본 캐릭터 반환 + 이벤트 발행
        if not characters:
            logger.info(
                "Empty character list, returning default and publishing event",
                extra={"user_id": str(user_id)},
            )
            return [self._get_default_character_dto(user_id)]

        # 3. DTO 변환
        return [_to_character_dto(char) for char in characters]

    def _get_default_character_dto(self, user_id: UUID) -> UserCharacterDTO:
        """기본 캐릭터 DTO를 생성하고 이벤트를 발행합니다."""
        # 이벤트 발행 (Fire-and-forget)
        if self._default_publisher:
            self._default_publisher.publish(user_id)

        # 설정에서 기본 캐릭터 정보 로드
        if self._settings:
            return UserCharacterDTO(
                id=UUID(self._settings.default_character_id),
                character_id=UUID(self._settings.default_character_id),
                character_code=self._settings.default_character_code,
                character_name=self._settings.default_character_name,
                character_type=self._settings.default_character_type,
                character_dialog=self._settings.default_character_dialog,
                source="default-onboard",
                status="owned",
                acquired_at=datetime.now(timezone.utc),
            )

        # Fallback (설정 없으면 하드코딩)
        return UserCharacterDTO(
            id=UUID("00000000-0000-0000-0000-000000000001"),
            character_id=UUID("00000000-0000-0000-0000-000000000001"),
            character_code="char-eco",
            character_name="이코",
            character_type="기본",
            character_dialog="안녕! 나는 이코야!",
            source="default-onboard",
            status="owned",
            acquired_at=datetime.now(timezone.utc),
        )


class CheckCharacterOwnershipQuery:
    """캐릭터 소유 여부 확인 Query (지휘자) - domains/my 호환.

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

    async def execute(self, user_id: UUID, character_name: str) -> CharacterOwnership:
        """특정 캐릭터의 소유 여부를 확인합니다.

        Args:
            user_id: 사용자 ID
            character_name: 캐릭터 이름

        Returns:
            소유 여부 DTO
        """
        logger.info(
            "Character ownership query executed",
            extra={"user_id": str(user_id), "character_name": character_name},
        )

        # 1. 캐릭터 소유 정보 조회 (Port 직접 호출)
        character = await self._character_gateway.get_by_character_name(user_id, character_name)

        # 2. 소유 여부 DTO 생성
        if character is None:
            return CharacterOwnership(
                character_name=character_name,
                owned=False,
            )

        return CharacterOwnership(
            character_name=character_name,
            owned=True,
        )
