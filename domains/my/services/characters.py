"""User character service - 사용자 캐릭터 인벤토리 관리.

이 서비스는 my 도메인의 user_characters 테이블을 사용합니다.
기본 캐릭터 지급 시 character 도메인의 gRPC를 호출하여 정보를 조회합니다.
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from domains.my.database.session import get_db_session
from domains.my.enums import UserCharacterStatus
from domains.my.models.user_character import UserCharacter as UserCharacterModel
from domains.my.repositories.user_character_repository import UserCharacterRepository
from domains.my.rpc.character_client import get_character_client
from domains.my.schemas import UserCharacter

logger = logging.getLogger(__name__)

DEFAULT_CHARACTER_SOURCE = "default-onboard"


class UserCharacterService:
    """사용자 캐릭터 인벤토리 서비스.

    my 도메인의 user_characters 테이블을 직접 사용합니다.
    기본 캐릭터 정보는 character 도메인 gRPC를 통해 조회합니다.
    """

    def __init__(self, session: AsyncSession = Depends(get_db_session)):
        self.session = session
        self.repo = UserCharacterRepository(session)

    async def list_owned(self, user_id: UUID) -> list[UserCharacter]:
        """사용자가 소유한 캐릭터 목록 조회.

        캐릭터가 없으면 기본 캐릭터(이코)를 자동으로 지급합니다.
        """
        ownerships = await self.repo.list_by_user(user_id)

        # 소유 캐릭터가 없으면 기본 캐릭터 자동 지급
        if not ownerships:
            granted = await self._ensure_default_character(user_id)
            if granted:
                ownerships = await self.repo.list_by_user(user_id)

        return [self._to_schema(entry) for entry in ownerships]

    async def _ensure_default_character(self, user_id: UUID) -> bool:
        """기본 캐릭터(이코)를 사용자에게 지급합니다.

        Returns:
            bool: 지급 성공 여부
        """
        try:
            # character 도메인에서 기본 캐릭터 정보 조회
            client = get_character_client()
            default_char = await client.get_default_character()

            if default_char is None:
                logger.error("Default character not found in character domain")
                return False

            # 이미 소유하고 있는지 확인
            existing = await self.repo.get_by_user_and_character(
                user_id=user_id,
                character_id=default_char.character_id,
            )
            if existing:
                logger.info("User %s already owns default character", user_id)
                return True

            # 새 캐릭터 지급
            new_ownership = UserCharacterModel(
                user_id=user_id,
                character_id=default_char.character_id,
                character_code=default_char.character_code,
                character_name=default_char.character_name,
                character_type=default_char.character_type or None,
                character_dialog=default_char.character_dialog or None,
                source=DEFAULT_CHARACTER_SOURCE,
                status=UserCharacterStatus.OWNED,
            )
            self.session.add(new_ownership)
            await self.session.commit()

            logger.info(
                "Granted default character %s to user %s",
                default_char.character_name,
                user_id,
            )
            return True

        except Exception as e:
            logger.exception(f"Failed to grant default character to user {user_id}: {e}")
            await self.session.rollback()
            return False

    async def owns_character(self, user_id: UUID, character_name: str) -> bool:
        """특정 캐릭터 소유 여부 확인."""
        normalized_name = character_name.strip()
        if not normalized_name:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Character name is required",
            )

        return await self.repo.owns_character_by_name(user_id, normalized_name)

    @staticmethod
    def _to_schema(entry: UserCharacterModel) -> UserCharacter:
        """ORM 모델을 스키마로 변환."""
        return UserCharacter(
            id=entry.character_id,
            code=entry.character_code,
            name=entry.character_name,
            type=entry.character_type or "",
            dialog=entry.character_dialog or "",
            acquired_at=entry.acquired_at,
        )
