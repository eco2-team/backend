"""Message Save Handler - 메시지 저장 핸들러.

Consumer Adapter가 디코딩한 메시지를 처리.
배치 단위로 모아서 Command 실행.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any, Awaitable, Callable

if TYPE_CHECKING:
    from chat.application.chat.commands.save_messages import SaveMessagesCommand

logger = logging.getLogger(__name__)


@dataclass
class CommandResult:
    """핸들러 결과."""

    is_success: bool
    is_retryable: bool = False
    should_drop: bool = False
    message: str = ""


class MessageSaveHandler:
    """메시지 저장 핸들러.

    배치 단위로 메시지를 모아서 Command 실행.
    """

    def __init__(
        self,
        command: "SaveMessagesCommand",
        batch_size: int = 100,
        batch_timeout: float = 5.0,
        on_commit: "Callable[[], Awaitable[None]] | None" = None,
    ) -> None:
        """초기화.

        Args:
            command: 메시지 저장 Command
            batch_size: 배치 크기 (기본 100)
            batch_timeout: 배치 타임아웃 (초, 기본 5초)
            on_commit: 배치 성공 후 커밋 콜백
        """
        self._command = command
        self._batch_size = batch_size
        self._batch_timeout = batch_timeout
        self._on_commit = on_commit
        self._batch: list[dict[str, Any]] = []
        self._last_flush: datetime = datetime.now()

    async def handle(self, data: dict[str, Any]) -> CommandResult:
        """개별 메시지 처리.

        배치에 추가하고, 배치 조건 충족 시 flush.

        Args:
            data: 메시지 데이터 (JSON 디코딩된)

        Returns:
            CommandResult
        """
        # 데이터 검증
        required_fields = [
            "conversation_id",
            "user_id",
            "user_message",
            "assistant_message",
        ]
        missing = [f for f in required_fields if f not in data]
        if missing:
            logger.warning(
                "Missing required fields, dropping message",
                extra={"missing": missing},
            )
            return CommandResult(
                is_success=False,
                should_drop=True,
                message=f"Missing fields: {missing}",
            )

        # 배치에 추가
        self._batch.append(data)

        # 배치 조건 확인
        should_flush = (
            len(self._batch) >= self._batch_size
            or self._seconds_since_last_flush() >= self._batch_timeout
        )

        if should_flush:
            return await self._flush_batch()

        # 아직 배치 미완성 - 성공으로 처리 (ack)
        return CommandResult(is_success=True)

    async def flush(self) -> CommandResult:
        """강제 flush (Consumer 종료 시 호출)."""
        if self._batch:
            return await self._flush_batch()
        return CommandResult(is_success=True)

    async def _flush_batch(self) -> CommandResult:
        """배치 저장 실행."""
        from chat.application.chat.commands.save_messages import MessageSaveInput

        if not self._batch:
            return CommandResult(is_success=True)

        # dict → DTO 변환
        events = []
        for data in self._batch:
            try:
                events.append(
                    MessageSaveInput(
                        conversation_id=data["conversation_id"],
                        user_id=data["user_id"],
                        user_message=data["user_message"],
                        user_message_created_at=datetime.fromisoformat(
                            data.get("user_message_created_at", datetime.now().isoformat())
                        ),
                        assistant_message=data["assistant_message"],
                        assistant_message_created_at=datetime.fromisoformat(
                            data.get("assistant_message_created_at", datetime.now().isoformat())
                        ),
                        intent=data.get("intent"),
                        metadata=data.get("metadata"),
                    )
                )
            except Exception as e:
                logger.warning(
                    "Failed to parse message event",
                    extra={"error": str(e)},
                )

        # Command 실행
        result = await self._command.execute(events)

        # 배치 초기화
        batch_size = len(self._batch)
        self._batch.clear()
        self._last_flush = datetime.now()

        if result.is_success:
            # 커밋 콜백 실행 (DB 트랜잭션 커밋)
            if self._on_commit:
                try:
                    await self._on_commit()
                except Exception as e:
                    logger.error("Commit failed", extra={"error": str(e)})
                    return CommandResult(
                        is_success=False,
                        is_retryable=True,
                        message=f"Commit failed: {e}",
                    )

            logger.info(
                "Batch flushed successfully",
                extra={
                    "batch_size": batch_size,
                    "saved_count": result.saved_count,
                },
            )
            return CommandResult(is_success=True)
        else:
            logger.error(
                "Batch flush failed",
                extra={"error": result.error},
            )
            return CommandResult(
                is_success=False,
                is_retryable=True,  # DB 오류 시 재시도
                message=result.error or "Batch save failed",
            )

    def _seconds_since_last_flush(self) -> float:
        """마지막 flush 이후 경과 시간."""
        return (datetime.now() - self._last_flush).total_seconds()

    @property
    def batch_size(self) -> int:
        """현재 배치 크기."""
        return len(self._batch)
