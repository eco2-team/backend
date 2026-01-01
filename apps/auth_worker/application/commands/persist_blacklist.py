"""Persist Blacklist Command.

블랙리스트 이벤트를 Redis에 저장하는 Use Case입니다.

블로그 참고: https://rooftopsnow.tistory.com/126
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from apps.auth_worker.application.common.dto.blacklist_event import BlacklistEvent
from apps.auth_worker.application.common.result import CommandResult

if TYPE_CHECKING:
    from apps.auth_worker.application.common.ports.blacklist_store import BlacklistStore

logger = logging.getLogger(__name__)


class PersistBlacklistCommand:
    """블랙리스트 저장 Command.

    Clean Architecture의 Use Case에 해당합니다.
    이벤트를 받아 Redis에 저장하는 단일 책임을 가집니다.

    CommandResult를 반환하여 Presentation Layer가 ack/nack을 결정할 수 있게 합니다.
    """

    def __init__(self, blacklist_store: "BlacklistStore") -> None:
        """Initialize.

        Args:
            blacklist_store: 블랙리스트 저장소 (DI)
        """
        self._store = blacklist_store

    async def execute(self, event: BlacklistEvent) -> CommandResult:
        """블랙리스트 이벤트 처리.

        Args:
            event: 블랙리스트 이벤트

        Returns:
            CommandResult: 실행 결과 (SUCCESS/RETRYABLE/DROP)
        """
        try:
            if event.type == "add":
                await self._handle_add(event)
            elif event.type == "remove":
                await self._handle_remove(event)
            else:
                logger.warning(
                    "Unknown event type",
                    extra={"type": event.type, "jti": event.jti[:8]},
                )
                # 알 수 없는 타입은 재시도해도 의미 없음 → DROP
                return CommandResult.drop(f"Unknown event type: {event.type}")

            return CommandResult.success()

        except (ConnectionError, TimeoutError, OSError) as e:
            # 일시적 실패 → 재시도 가능
            logger.warning(
                "Temporary failure, will retry",
                extra={"error": str(e), "jti": event.jti[:8]},
            )
            return CommandResult.retryable(str(e))

        except ValueError as e:
            # 영구적 실패 → 재시도 무의미
            logger.error(
                "Permanent failure, dropping message",
                extra={"error": str(e), "jti": event.jti[:8]},
            )
            return CommandResult.drop(str(e))

    async def _handle_add(self, event: BlacklistEvent) -> None:
        """블랙리스트 추가 처리."""
        await self._store.add(
            jti=event.jti,
            expires_at=event.expires_at,
            user_id=event.user_id,
            reason=event.reason,
        )
        logger.info(
            "Token blacklisted",
            extra={
                "jti": event.jti[:8],
                "user_id": event.user_id[:8] if event.user_id else None,
                "reason": event.reason,
            },
        )

    async def _handle_remove(self, event: BlacklistEvent) -> None:
        """블랙리스트 제거 처리."""
        await self._store.remove(event.jti)
        logger.info(
            "Token removed from blacklist",
            extra={"jti": event.jti[:8]},
        )
