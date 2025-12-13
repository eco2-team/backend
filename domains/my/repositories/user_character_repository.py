"""User character repository - 사용자 캐릭터 소유 정보 저장소.

TODO: character 도메인 분리 후 활성화
현재는 character.character_ownerships를 직접 사용 중
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from domains.my.enums import UserCharacterStatus
from domains.my.models.user_character import UserCharacter


class UserCharacterRepository:
    """사용자 캐릭터 소유 정보 데이터 액세스 레이어."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def grant_character(
        self,
        *,
        user_id: UUID,
        character_id: UUID,
        character_code: str,
        character_name: str,
        source: str | None = None,
    ) -> UserCharacter:
        """캐릭터 지급 (upsert).

        이미 소유 중이면 상태를 OWNED로 업데이트,
        없으면 새로 생성.
        """
        existing = await self.get_by_user_and_character(user_id, character_id)

        if existing:
            existing.status = UserCharacterStatus.OWNED
            if source:
                existing.source = source
            existing.updated_at = datetime.now(timezone.utc)
            await self.session.flush()
            return existing

        user_char = UserCharacter(
            user_id=user_id,
            character_id=character_id,
            character_code=character_code,
            character_name=character_name,
            source=source,
            status=UserCharacterStatus.OWNED,
        )
        self.session.add(user_char)
        await self.session.flush()
        return user_char

    async def list_by_user(
        self,
        user_id: UUID,
        *,
        status: UserCharacterStatus = UserCharacterStatus.OWNED,
    ) -> list[UserCharacter]:
        """사용자의 캐릭터 목록 조회."""
        stmt = (
            select(UserCharacter)
            .where(
                UserCharacter.user_id == user_id,
                UserCharacter.status == status,
            )
            .order_by(UserCharacter.acquired_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_user_and_character(
        self,
        user_id: UUID,
        character_id: UUID,
    ) -> UserCharacter | None:
        """특정 캐릭터 소유 여부 확인."""
        stmt = select(UserCharacter).where(
            UserCharacter.user_id == user_id,
            UserCharacter.character_id == character_id,
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def owns_character(self, user_id: UUID, character_id: UUID) -> bool:
        """캐릭터 소유 여부 확인 (boolean)."""
        ownership = await self.get_by_user_and_character(user_id, character_id)
        return ownership is not None and ownership.status == UserCharacterStatus.OWNED

    async def burn_character(self, user_id: UUID, character_id: UUID) -> bool:
        """캐릭터 소각 (soft delete)."""
        ownership = await self.get_by_user_and_character(user_id, character_id)
        if not ownership:
            return False

        ownership.status = UserCharacterStatus.BURNED
        ownership.updated_at = datetime.now(timezone.utc)
        await self.session.flush()
        return True

    async def count_by_user(
        self,
        user_id: UUID,
        *,
        status: UserCharacterStatus = UserCharacterStatus.OWNED,
    ) -> int:
        """사용자의 캐릭터 수 조회."""
        chars = await self.list_by_user(user_id, status=status)
        return len(chars)
