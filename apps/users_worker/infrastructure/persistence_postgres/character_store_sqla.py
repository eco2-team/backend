"""SQLAlchemy Character Store.

users.user_characters 테이블에 BULK UPSERT를 수행합니다.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from apps.users_worker.application.character.dto.event import CharacterEvent

logger = logging.getLogger(__name__)


class SqlaCharacterStore:
    """SQLAlchemy 기반 캐릭터 저장소.

    users.user_characters 테이블에 BULK UPSERT를 수행합니다.

    멱등성 보장:
        - (user_id, character_code) 기준으로 중복 방지
        - character_id는 최신 값으로 갱신 (self-healing)
    """

    def __init__(self, session: AsyncSession) -> None:
        """Initialize.

        Args:
            session: SQLAlchemy AsyncSession
        """
        self._session = session

    async def bulk_upsert(self, events: list["CharacterEvent"]) -> int:
        """캐릭터 배치 UPSERT.

        INSERT INTO users.user_characters ...
        ON CONFLICT (user_id, character_code) DO UPDATE SET ...

        Args:
            events: 저장할 캐릭터 이벤트 목록

        Returns:
            처리된 레코드 수

        Raises:
            ConnectionError: DB 연결 실패
            TimeoutError: DB 타임아웃
        """
        if not events:
            return 0

        # Bulk UPSERT (character_code 기준)
        values = []
        params: dict = {}

        for i, event in enumerate(events):
            values.append(
                f"(:user_id_{i}, :character_id_{i}, :character_code_{i}, "
                f":character_name_{i}, :character_type_{i}, :character_dialog_{i}, "
                f":source_{i}, :status_{i}, NOW(), NOW())"
            )
            params[f"user_id_{i}"] = event.user_id
            params[f"character_id_{i}"] = event.character_id
            params[f"character_code_{i}"] = event.character_code
            params[f"character_name_{i}"] = event.character_name
            params[f"character_type_{i}"] = event.character_type
            params[f"character_dialog_{i}"] = event.character_dialog
            params[f"source_{i}"] = event.source
            params[f"status_{i}"] = "owned"

        # character_code 기준 UPSERT
        # - 동일 (user_id, character_code) 존재 시: character_id를 최신으로 갱신
        # - 신규: INSERT
        sql = text(
            f"""
            INSERT INTO users.user_characters
                (user_id, character_id, character_code, character_name,
                 character_type, character_dialog, source, status, acquired_at, updated_at)
            VALUES {", ".join(values)}
            ON CONFLICT (user_id, character_code) DO UPDATE SET
                character_id = EXCLUDED.character_id,
                character_name = EXCLUDED.character_name,
                character_type = COALESCE(EXCLUDED.character_type, users.user_characters.character_type),
                character_dialog = COALESCE(EXCLUDED.character_dialog, users.user_characters.character_dialog),
                updated_at = NOW()
            """
        )

        try:
            result = await self._session.execute(sql, params)
            await self._session.commit()

            logger.debug(
                "Bulk upsert completed",
                extra={"batch_size": len(events), "rowcount": result.rowcount},
            )

            return result.rowcount

        except Exception as e:
            await self._session.rollback()
            logger.error(
                "Bulk upsert failed",
                extra={"error": str(e), "batch_size": len(events)},
            )
            raise
