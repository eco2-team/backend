"""Blacklist Handler.

메시지를 검증하고 Command를 호출하는 Presentation Layer 컴포넌트입니다.

블로그 참고: https://rooftopsnow.tistory.com/126

Handler의 책임:
1. 메시지 검증 (Pydantic Schema)
2. Application DTO 변환
3. Command 호출
4. CommandResult 전달

Handler가 하지 않는 것:
- ack/nack 결정 (ConsumerAdapter에서)
- 업무 성공/실패 판단 (Command에서)
- 리트라이 정책 결정 (Command에서)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from apps.auth_worker.application.common.dto.blacklist_event import BlacklistEvent
from apps.auth_worker.application.common.result import CommandResult

if TYPE_CHECKING:
    from apps.auth_worker.application.commands.persist_blacklist import (
        PersistBlacklistCommand,
    )

logger = logging.getLogger(__name__)


class BlacklistHandler:
    """블랙리스트 메시지 핸들러.

    메시지 → Command 파이프라인을 담당합니다.
    """

    def __init__(self, command: "PersistBlacklistCommand") -> None:
        """Initialize.

        Args:
            command: 블랙리스트 저장 Command (DI)
        """
        self._command = command

    async def handle(self, data: dict[str, Any]) -> CommandResult:
        """메시지 처리.

        Args:
            data: JSON 디코딩된 메시지 데이터

        Returns:
            CommandResult: Command 실행 결과
        """
        try:
            # 1. Application DTO 변환 (검증 포함)
            event = BlacklistEvent.from_dict(data)

            # 2. Command 호출
            result = await self._command.execute(event)

            # 3. CommandResult 전달
            return result

        except (KeyError, TypeError, ValueError) as e:
            # 메시지 형식 오류 → 재시도 무의미
            logger.error(
                "Invalid message format",
                extra={"error": str(e), "data": data},
            )
            return CommandResult.drop(f"Invalid message format: {e}")

        except Exception as e:
            # 예상치 못한 오류 → 재시도 가능
            logger.exception("Unexpected error handling message")
            return CommandResult.retryable(str(e))
