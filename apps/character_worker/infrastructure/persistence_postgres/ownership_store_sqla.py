"""SQLAlchemy Ownership Store Implementation.

멱등성: (user_id, character_code) UNIQUE - users.user_characters와 통일

Ref: https://rooftopsnow.tistory.com/132
"""

import logging
from typing import Sequence
from uuid import NAMESPACE_DNS, UUID, uuid5

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from character_worker.application.ownership.dto import OwnershipEvent
from character_worker.application.ownership.ports import OwnershipStore

logger = logging.getLogger(__name__)


def _deterministic_uuid(user_id: UUID, character_code: str) -> UUID:
    """결정적 UUID를 생성합니다.

    동일한 (user_id, character_code) 조합에 대해 항상 같은 UUID를 생성합니다.
    멱등성 보장에 사용됩니다.
    """
    return uuid5(NAMESPACE_DNS, f"ownership:{user_id}:{character_code}")


class SqlaOwnershipStore(OwnershipStore):
    """SQLAlchemy 기반 소유권 저장소.

    character.character_ownerships 테이블에 저장합니다.
    """

    def __init__(self, session: AsyncSession) -> None:
        """Initialize.

        Args:
            session: SQLAlchemy 비동기 세션
        """
        self._session = session

    async def bulk_insert_ignore(self, events: Sequence[OwnershipEvent]) -> int:
        """여러 소유권을 일괄 저장합니다.

        ON CONFLICT (user_id, character_code) DO NOTHING으로 중복을 무시합니다.
        """
        if not events:
            return 0

        # 결정적 UUID로 데이터 준비 (character_code 기준)
        values = []
        for event in events:
            row_id = _deterministic_uuid(event.user_id, event.character_code)
            values.append(
                {
                    "id": str(row_id),
                    "user_id": str(event.user_id),
                    "character_id": str(event.character_id),
                    "character_code": event.character_code,
                    "source": event.source,
                }
            )

        # Bulk INSERT with character_code
        stmt = text(
            """
            INSERT INTO character.character_ownerships
                (id, user_id, character_id, character_code, source, status, acquired_at, updated_at)
            VALUES
                (:id, :user_id, :character_id, :character_code, :source, 'owned', NOW(), NOW())
            ON CONFLICT (user_id, character_code) DO NOTHING
        """
        )

        inserted = 0
        for value in values:
            result = await self._session.execute(stmt, value)
            if result.rowcount > 0:
                inserted += 1

        await self._session.commit()

        logger.debug(
            "Bulk insert completed",
            extra={"total": len(events), "inserted": inserted},
        )

        return inserted
