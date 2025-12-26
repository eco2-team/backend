"""User character repository - 사용자 캐릭터 소유 정보 저장소.

Single-query UPSERT 패턴을 사용하여 멱등성을 보장합니다.
- INSERT ... ON CONFLICT DO UPDATE
- Race condition 없음 (atomic)
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
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
        character_type: str | None = None,
        character_dialog: str | None = None,
        source: str | None = None,
    ) -> UserCharacter:
        """캐릭터 지급 (Single-query UPSERT).

        INSERT ... ON CONFLICT DO UPDATE 사용:
        - 신규: INSERT
        - 기존: status를 OWNED로 업데이트
        - Race condition 없음 (atomic)
        """
        stmt = (
            insert(UserCharacter)
            .values(
                user_id=user_id,
                character_id=character_id,
                character_code=character_code,
                character_name=character_name,
                character_type=character_type,
                character_dialog=character_dialog,
                source=source,
                status=UserCharacterStatus.OWNED,
                acquired_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
            .on_conflict_do_update(
                constraint="uq_user_character",
                set_={
                    "status": UserCharacterStatus.OWNED,
                    "source": source,
                    "updated_at": datetime.now(timezone.utc),
                },
            )
            .returning(UserCharacter)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one()

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

    async def owns_character_by_name(self, user_id: UUID, character_name: str) -> bool:
        """캐릭터 이름으로 소유 여부 확인."""
        stmt = select(UserCharacter).where(
            UserCharacter.user_id == user_id,
            UserCharacter.character_name == character_name,
            UserCharacter.status == UserCharacterStatus.OWNED,
        )
        result = await self.session.execute(stmt)
        return result.scalars().first() is not None
