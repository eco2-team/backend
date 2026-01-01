"""Relay Loop.

Outbox 폴링 및 이벤트 재발행을 담당하는 Presentation 컴포넌트입니다.

Architecture:
    RelayLoop (Presentation)
        │
        │ event_json
        ▼
    RelayEventCommand (Application)
        │
        │ RelayResult
        ▼
    RelayLoop
        │
        └── re-queue / DLQ / continue
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from apps.auth_relay.application.commands.relay_event import RelayEventCommand
    from apps.auth_relay.application.common.ports.outbox_reader import OutboxReader

logger = logging.getLogger(__name__)


class RelayLoop:
    """Relay 폴링 루프.

    Outbox에서 이벤트를 읽어 Command로 전달하고,
    결과에 따라 re-queue 또는 DLQ 처리를 합니다.
    """

    def __init__(
        self,
        outbox_reader: "OutboxReader",
        relay_command: "RelayEventCommand",
        *,
        poll_interval: float = 1.0,
        batch_size: int = 10,
    ) -> None:
        """Initialize.

        Args:
            outbox_reader: Outbox 읽기 포트
            relay_command: 재발행 Command
            poll_interval: 폴링 간격 (초)
            batch_size: 배치 크기
        """
        self._outbox_reader = outbox_reader
        self._relay_command = relay_command
        self._poll_interval = poll_interval
        self._batch_size = batch_size
        self._shutdown = False
        self._processed_total = 0
        self._failed_total = 0

    async def run(self) -> None:
        """메인 폴링 루프 실행."""
        depth = await self._outbox_reader.length()
        logger.info(
            "Starting relay loop",
            extra={
                "poll_interval": self._poll_interval,
                "batch_size": self._batch_size,
                "initial_queue_depth": depth,
            },
        )

        while not self._shutdown:
            try:
                processed = await self._process_batch()
                if processed == 0:
                    await asyncio.sleep(self._poll_interval)
            except Exception:
                logger.exception("Relay loop error")
                await asyncio.sleep(self._poll_interval * 2)

    async def _process_batch(self) -> int:
        """배치 처리.

        Returns:
            처리된 이벤트 수
        """
        processed = 0

        for _ in range(self._batch_size):
            event_json = await self._outbox_reader.pop()
            if not event_json:
                break

            result = await self._relay_command.execute(event_json)

            if result.is_success:
                processed += 1
                self._processed_total += 1

            elif result.is_retryable:
                # 재시도를 위해 큐 앞에 다시 삽입
                await self._outbox_reader.push_back(event_json)
                logger.warning(
                    "Event re-queued for retry",
                    extra={"reason": result.message},
                )
                # MQ 문제일 가능성이 높으므로 배치 중단
                break

            elif result.should_drop:
                # DLQ로 이동
                await self._outbox_reader.push_to_dlq(event_json)
                self._failed_total += 1

        if processed > 0:
            logger.info(
                "Batch processed",
                extra={
                    "processed": processed,
                    "total_processed": self._processed_total,
                    "total_failed": self._failed_total,
                },
            )

        return processed

    def stop(self) -> None:
        """루프 종료."""
        logger.info("Relay loop stopping")
        self._shutdown = True

    @property
    def stats(self) -> dict[str, int]:
        """통계 반환."""
        return {
            "processed": self._processed_total,
            "failed": self._failed_total,
        }
