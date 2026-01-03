"""SaveOwnershipCommand.

캐릭터 소유권 저장 Command입니다.
"""

import logging
from typing import Sequence

from sqlalchemy.exc import OperationalError

from apps.character_worker.application.ownership.dto import (
    OwnershipEvent,
    SaveOwnershipResult,
)
from apps.character_worker.application.ownership.ports import OwnershipStore

logger = logging.getLogger(__name__)


class SaveOwnershipCommand:
    """캐릭터 소유권 저장 Command.

    Celery Batches로 모은 이벤트를 일괄 저장합니다.
    ON CONFLICT DO NOTHING으로 멱등성을 보장합니다.
    """

    def __init__(self, store: OwnershipStore) -> None:
        """Initialize.

        Args:
            store: 소유권 저장소
        """
        self._store = store

    async def execute(self, events: Sequence[OwnershipEvent]) -> SaveOwnershipResult:
        """소유권을 저장합니다.

        Args:
            events: 소유권 이벤트 목록

        Returns:
            저장 결과
        """
        if not events:
            return SaveOwnershipResult(success=True)

        try:
            inserted = await self._store.bulk_insert_ignore(events)
            skipped = len(events) - inserted

            logger.info(
                "Ownership saved",
                extra={
                    "total": len(events),
                    "inserted": inserted,
                    "skipped": skipped,
                },
            )

            return SaveOwnershipResult(
                success=True,
                inserted=inserted,
                skipped=skipped,
            )

        except OperationalError as e:
            # DB 연결 실패 등 일시적 오류 - 재시도 필요
            logger.warning(
                "Temporary failure saving ownership, will retry",
                extra={"error": str(e), "count": len(events)},
            )
            return SaveOwnershipResult(
                success=False,
                failed=len(events),
                should_retry=True,
            )

        except Exception as e:
            # 영구적 오류 - 재시도 불필요
            logger.error(
                "Permanent failure saving ownership",
                extra={"error": str(e), "count": len(events)},
            )
            return SaveOwnershipResult(
                success=False,
                failed=len(events),
                should_retry=False,
            )
