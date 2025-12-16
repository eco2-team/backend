"""User character service - 사용자 캐릭터 인벤토리 관리.

이 서비스는 my 도메인의 user_characters 테이블을 사용합니다.
character 도메인에 대한 직접 의존 없이 독립적으로 동작합니다.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from domains.my.database.session import get_db_session
from domains.my.models.user_character import UserCharacter as UserCharacterModel
from domains.my.repositories.user_character_repository import UserCharacterRepository
from domains.my.schemas import UserCharacter

# 기본 캐릭터 정보 (character 도메인과 동기화 필요)
DEFAULT_CHARACTER_CODE = "CHAR_001"
DEFAULT_CHARACTER_NAME = "그로비"
DEFAULT_CHARACTER_SOURCE = "onboarding"


class UserCharacterService:
    """사용자 캐릭터 인벤토리 서비스.

    my 도메인의 user_characters 테이블을 직접 사용합니다.
    """

    def __init__(self, session: AsyncSession = Depends(get_db_session)):
        self.session = session
        self.repo = UserCharacterRepository(session)

    async def list_owned(self, user_id: UUID) -> list[UserCharacter]:
        """사용자가 소유한 캐릭터 목록 조회."""
        ownerships = await self.repo.list_by_user(user_id)

        # 소유 캐릭터가 없으면 빈 리스트 반환
        # NOTE: 기본 캐릭터 자동 지급은 character 도메인에서 gRPC로 처리
        if not ownerships:
            return []

        return [self._to_schema(entry) for entry in ownerships]

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
