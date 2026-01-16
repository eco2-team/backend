"""Save Messages Command - 메시지 배치 저장 유스케이스.

Eventual Consistency 패턴에서 Consumer가 사용.
Worker 완료 후 큐에 쌓인 메시지를 배치로 저장.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

if TYPE_CHECKING:
    from chat.application.chat.ports.chat_repository import ChatRepositoryPort

logger = logging.getLogger(__name__)


@dataclass
class MessageSaveInput:
    """메시지 저장 입력 DTO."""

    conversation_id: str
    user_id: str
    user_message: str
    user_message_created_at: datetime
    assistant_message: str
    assistant_message_created_at: datetime
    intent: str | None = None
    metadata: dict[str, Any] | None = None


@dataclass
class SaveMessagesResult:
    """배치 저장 결과."""

    saved_count: int
    updated_conversations: int
    is_success: bool
    error: str | None = None


class SaveMessagesCommand:
    """메시지 배치 저장 Command.

    Eventual Consistency Consumer에서 호출.
    배치 단위로 메시지 저장 + Conversation 메타 업데이트.
    """

    def __init__(self, repository: "ChatRepositoryPort") -> None:
        """초기화.

        Args:
            repository: Chat Repository
        """
        self._repository = repository

    async def execute(self, events: list[MessageSaveInput]) -> SaveMessagesResult:
        """메시지 배치 저장 실행.

        Args:
            events: 저장할 메시지 이벤트 목록

        Returns:
            저장 결과
        """
        from uuid import uuid4

        from chat.domain.entities.message import Message

        if not events:
            return SaveMessagesResult(
                saved_count=0,
                updated_conversations=0,
                is_success=True,
            )

        try:
            # 1. 메시지 엔티티 생성 (user + assistant 쌍)
            messages: list[Message] = []
            # conversation별 마지막 메시지 정보 (preview, timestamp)
            conv_updates: dict[str, tuple[str, datetime, int]] = {}

            for event in events:
                chat_id = UUID(event.conversation_id)

                # User message
                user_msg = Message(
                    id=uuid4(),
                    chat_id=chat_id,
                    role="user",
                    content=event.user_message,
                    created_at=event.user_message_created_at,
                )
                messages.append(user_msg)

                # Assistant message
                assistant_msg = Message(
                    id=uuid4(),
                    chat_id=chat_id,
                    role="assistant",
                    content=event.assistant_message,
                    intent=event.intent,
                    metadata=event.metadata,
                    created_at=event.assistant_message_created_at,
                )
                messages.append(assistant_msg)

                # Conversation 메타 업데이트 정보 수집
                conv_id = event.conversation_id
                if conv_id not in conv_updates:
                    conv_updates[conv_id] = (
                        event.assistant_message,
                        event.assistant_message_created_at,
                        2,  # user + assistant
                    )
                else:
                    # 같은 conversation에 여러 이벤트가 있는 경우
                    # 가장 최신 메시지로 업데이트
                    _, prev_ts, prev_count = conv_updates[conv_id]
                    if event.assistant_message_created_at > prev_ts:
                        conv_updates[conv_id] = (
                            event.assistant_message,
                            event.assistant_message_created_at,
                            prev_count + 2,
                        )
                    else:
                        conv_updates[conv_id] = (
                            conv_updates[conv_id][0],
                            conv_updates[conv_id][1],
                            prev_count + 2,
                        )

            # 2. Bulk INSERT messages
            saved_count = await self._repository.bulk_create_messages(messages)

            # 3. Conversation 메타데이터 업데이트
            updated_conversations = 0
            for conv_id, (preview, last_msg_at, msg_count) in conv_updates.items():
                try:
                    updated = await self._repository.update_conversation_metadata(
                        chat_id=UUID(conv_id),
                        message_count_delta=msg_count,
                        preview=preview,
                        last_message_at=last_msg_at,
                    )
                    if updated:
                        updated_conversations += 1
                except Exception as e:
                    logger.warning(
                        "Failed to update conversation metadata",
                        extra={"conversation_id": conv_id, "error": str(e)},
                    )

            logger.info(
                "Messages batch saved",
                extra={
                    "saved_count": saved_count,
                    "updated_conversations": updated_conversations,
                    "event_count": len(events),
                },
            )

            return SaveMessagesResult(
                saved_count=saved_count,
                updated_conversations=updated_conversations,
                is_success=True,
            )

        except Exception as e:
            logger.error(
                "Messages batch save failed",
                extra={"error": str(e)},
                exc_info=True,
            )
            return SaveMessagesResult(
                saved_count=0,
                updated_conversations=0,
                is_success=False,
                error=str(e),
            )
