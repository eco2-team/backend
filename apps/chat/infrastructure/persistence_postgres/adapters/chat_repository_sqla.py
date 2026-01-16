"""Chat Repository SQLAlchemy Adapter.

ChatRepositoryPort의 PostgreSQL 구현체.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from chat.application.chat.ports.chat_repository import ChatRepositoryPort
from chat.domain.entities.chat import Chat
from chat.domain.entities.message import Message
from chat.infrastructure.persistence_postgres.mappings.chat import conversations_table
from chat.infrastructure.persistence_postgres.mappings.message import messages_table

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class ChatRepositorySQLA(ChatRepositoryPort):
    """Chat Repository SQLAlchemy 구현체."""

    def __init__(self, session: "AsyncSession") -> None:
        """초기화.

        Args:
            session: SQLAlchemy AsyncSession
        """
        self._session = session

    # ─────────────────────────────────────────────────────────────
    # Chat (세션) 관련
    # ─────────────────────────────────────────────────────────────

    async def get_chats_by_user(
        self,
        user_id: UUID,
        limit: int = 20,
        cursor: str | None = None,
    ) -> tuple[list[Chat], str | None]:
        """사용자의 채팅 목록 조회 (사이드바용)."""
        stmt = (
            select(Chat)
            .where(
                conversations_table.c.user_id == user_id,
                conversations_table.c.is_deleted == False,  # noqa: E712
            )
            .order_by(conversations_table.c.last_message_at.desc().nulls_last())
            .limit(limit + 1)
        )

        # 커서 기반 페이징
        if cursor:
            from datetime import datetime

            cursor_time = datetime.fromisoformat(cursor)
            stmt = stmt.where(conversations_table.c.last_message_at < cursor_time)

        result = await self._session.execute(stmt)
        chats = list(result.scalars().all())

        # 다음 페이지 확인
        next_cursor = None
        if len(chats) > limit:
            chats = chats[:limit]
            if chats[-1].last_message_at:
                next_cursor = chats[-1].last_message_at.isoformat()

        return chats, next_cursor

    async def get_chat_by_id(self, chat_id: UUID) -> Chat | None:
        """채팅 상세 조회."""
        stmt = select(Chat).where(
            conversations_table.c.id == chat_id,
            conversations_table.c.is_deleted == False,  # noqa: E712
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def create_chat(self, chat: Chat) -> Chat:
        """새 채팅 생성."""
        self._session.add(chat)
        await self._session.flush()
        await self._session.refresh(chat)
        return chat

    async def update_chat(self, chat: Chat) -> Chat:
        """채팅 업데이트."""
        await self._session.flush()
        await self._session.refresh(chat)
        return chat

    async def delete_chat(self, chat_id: UUID) -> bool:
        """채팅 삭제 (soft delete)."""
        stmt = update(Chat).where(conversations_table.c.id == chat_id).values(is_deleted=True)
        result = await self._session.execute(stmt)
        await self._session.flush()
        return result.rowcount > 0

    # ─────────────────────────────────────────────────────────────
    # Message 관련
    # ─────────────────────────────────────────────────────────────

    async def get_messages_by_chat(
        self,
        chat_id: UUID,
        limit: int = 50,
        before: str | None = None,
    ) -> tuple[list[Message], bool]:
        """채팅의 메시지 목록 조회."""
        stmt = (
            select(Message)
            .where(messages_table.c.chat_id == chat_id)
            .order_by(messages_table.c.created_at.asc())
            .limit(limit + 1)
        )

        # 시간 기반 페이징
        if before:
            from datetime import datetime

            before_time = datetime.fromisoformat(before)
            stmt = stmt.where(messages_table.c.created_at < before_time)

        result = await self._session.execute(stmt)
        messages = list(result.scalars().all())

        # 더 있는지 확인
        has_more = len(messages) > limit
        if has_more:
            messages = messages[:limit]

        return messages, has_more

    async def create_message(self, message: Message) -> Message:
        """새 메시지 생성."""
        self._session.add(message)
        await self._session.flush()
        await self._session.refresh(message)
        return message

    async def get_message_by_job_id(self, job_id: UUID) -> Message | None:
        """job_id로 메시지 조회."""
        stmt = select(Message).where(messages_table.c.job_id == job_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def update_message(self, message: Message) -> Message:
        """메시지 업데이트."""
        await self._session.flush()
        await self._session.refresh(message)
        return message

    # ─────────────────────────────────────────────────────────────
    # Batch 관련 (Eventual Consistency Consumer용)
    # ─────────────────────────────────────────────────────────────

    async def bulk_create_messages(self, messages: list[Message]) -> int:
        """메시지 일괄 생성 (배치 Consumer용).

        PostgreSQL INSERT ... ON CONFLICT DO NOTHING 사용.
        이미 존재하는 메시지는 무시 (idempotent).
        """
        if not messages:
            return 0

        # Entity → dict 변환
        values = [
            {
                "id": msg.id,
                "chat_id": msg.chat_id,
                "role": msg.role,
                "content": msg.content,
                "intent": msg.intent,
                "metadata": msg.metadata,
                "job_id": msg.job_id,
                "created_at": msg.created_at,
            }
            for msg in messages
        ]

        # Bulk INSERT with ON CONFLICT DO NOTHING (idempotent)
        stmt = (
            pg_insert(messages_table).values(values).on_conflict_do_nothing(index_elements=["id"])
        )

        result = await self._session.execute(stmt)
        await self._session.flush()

        return result.rowcount

    async def update_conversation_metadata(
        self,
        chat_id: UUID,
        message_count_delta: int,
        preview: str,
        last_message_at: datetime,
    ) -> bool:
        """Conversation 메타데이터 업데이트."""
        # 메시지 수 증분, preview, last_message_at 업데이트
        stmt = (
            update(conversations_table)
            .where(conversations_table.c.id == chat_id)
            .values(
                message_count=conversations_table.c.message_count + message_count_delta,
                preview=preview[:100] if len(preview) > 100 else preview,
                last_message_at=last_message_at,
                updated_at=datetime.now(),
            )
        )

        result = await self._session.execute(stmt)
        await self._session.flush()

        return result.rowcount > 0
