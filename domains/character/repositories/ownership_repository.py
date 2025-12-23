from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from domains.character.enums import CharacterOwnershipStatus
from domains.character.models import Character, CharacterOwnership


class CharacterOwnershipRepository:
    """Data access helper for tracking user character ownership."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def insert_owned(
        self,
        *,
        user_id: UUID,
        character: Character,
        source: str | None = None,
    ) -> CharacterOwnership:
        """새 ownership INSERT (SELECT 없이 직접 삽입).

        Note:
            호출 전 ownership 존재 여부를 이미 확인했을 때 사용.
            중복 시 IntegrityError 발생 (UniqueConstraint).
        """
        ownership = CharacterOwnership(
            user_id=user_id,
            character_id=character.id,
            source=source,
            status=CharacterOwnershipStatus.OWNED,
        )
        ownership.character = character
        self.session.add(ownership)
        await self.session.flush()
        return ownership

    async def list_by_user(self, user_id: UUID) -> list[CharacterOwnership]:
        stmt = (
            select(CharacterOwnership)
            .options(selectinload(CharacterOwnership.character))
            .where(
                CharacterOwnership.user_id == user_id,
                CharacterOwnership.status == CharacterOwnershipStatus.OWNED,
            )
            .order_by(CharacterOwnership.acquired_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_user_and_character(
        self, user_id: UUID, character_id: UUID
    ) -> CharacterOwnership | None:
        return await self._get_internal(user_id=user_id, character_id=character_id)

    async def _get_internal(self, user_id: UUID, character_id: UUID) -> CharacterOwnership | None:
        stmt = (
            select(CharacterOwnership)
            .options(selectinload(CharacterOwnership.character))
            .where(
                CharacterOwnership.user_id == user_id,
                CharacterOwnership.character_id == character_id,
            )
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def insert_or_ignore(
        self,
        *,
        user_id: UUID,
        character_id: UUID,
        source: str | None = None,
    ) -> bool:
        """멱등적 삽입: 이미 존재하면 무시.

        ON CONFLICT DO NOTHING을 사용하여 중복 삽입을 방지합니다.
        여러 번 호출해도 안전합니다 (멱등성).

        Args:
            user_id: 사용자 ID
            character_id: 캐릭터 ID
            source: 획득 소스 (예: "scan-reward")

        Returns:
            True면 새로 삽입됨, False면 이미 존재하여 무시됨
        """
        stmt = (
            insert(CharacterOwnership)
            .values(
                user_id=user_id,
                character_id=character_id,
                source=source,
                status=CharacterOwnershipStatus.OWNED,
                acquired_at=datetime.now(timezone.utc),
            )
            .on_conflict_do_nothing(index_elements=["user_id", "character_id"])
        )
        result = await self.session.execute(stmt)
        await self.session.commit()
        # rowcount > 0이면 새로 삽입됨
        return result.rowcount > 0
