"""Save Characters Command.

캐릭터 배치 저장 Use Case입니다.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from apps.users_worker.application.common.result import CommandResult

if TYPE_CHECKING:
    from apps.users_worker.application.character.dto.event import CharacterEvent
    from apps.users_worker.application.character.ports.store import CharacterStore

logger = logging.getLogger(__name__)


class SaveCharactersCommand:
    """캐릭터 저장 Command.

    Clean Architecture의 Use Case에 해당합니다.
    배치 이벤트를 받아 DB에 저장하는 단일 책임을 가집니다.

    CommandResult를 반환하여 Presentation Layer가
    Celery retry/success를 결정할 수 있게 합니다.
    """

    def __init__(self, character_store: "CharacterStore") -> None:
        """Initialize.

        Args:
            character_store: 캐릭터 저장소 (DI)
        """
        self._store = character_store

    async def execute(self, events: list["CharacterEvent"]) -> CommandResult:
        """캐릭터 배치 저장.

        Args:
            events: 저장할 캐릭터 이벤트 목록

        Returns:
            CommandResult: 실행 결과 (SUCCESS/RETRYABLE/DROP)
        """
        if not events:
            return CommandResult.success(processed=0, upserted=0)

        try:
            upserted = await self._store.bulk_upsert(events)

            logger.info(
                "Characters saved",
                extra={
                    "processed": len(events),
                    "upserted": upserted,
                },
            )

            return CommandResult.success(processed=len(events), upserted=upserted)

        except (ConnectionError, TimeoutError, OSError) as e:
            # 일시적 실패 → 재시도 가능
            logger.warning(
                "Temporary failure, will retry",
                extra={"error": str(e), "batch_size": len(events)},
            )
            return CommandResult.retryable(str(e))

        except ValueError as e:
            # 영구적 실패 → 재시도 무의미
            logger.error(
                "Permanent failure, dropping batch",
                extra={"error": str(e), "batch_size": len(events)},
            )
            return CommandResult.drop(str(e))
