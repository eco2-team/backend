"""Message ORM Mapping - Imperative mapping for chat.messages table.

메시지 히스토리 테이블 매핑.
"""

from __future__ import annotations

from sqlalchemy import Column, DateTime, Table, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID

from chat.domain.entities.message import Message
from chat.infrastructure.persistence_postgres.constants import MESSAGES_TABLE
from chat.infrastructure.persistence_postgres.registry import (
    mapper_registry,
    metadata,
)

# chat.messages 테이블 정의
messages_table = Table(
    MESSAGES_TABLE,
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("chat_id", UUID(as_uuid=True), nullable=False),
    Column("role", Text, nullable=False),
    Column("content", Text, nullable=False),
    Column("intent", Text, nullable=True),
    Column("metadata", JSONB, nullable=True),
    Column("job_id", UUID(as_uuid=True), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)


def start_message_mapper() -> None:
    """Message 엔티티를 chat.messages 테이블에 매핑합니다."""
    if hasattr(Message, "__mapper__"):
        return

    mapper_registry.map_imperatively(
        Message,
        messages_table,
        properties={
            "id": messages_table.c.id,
            "chat_id": messages_table.c.chat_id,
            "role": messages_table.c.role,
            "content": messages_table.c.content,
            "intent": messages_table.c.intent,
            "metadata": messages_table.c.metadata,
            "job_id": messages_table.c.job_id,
            "created_at": messages_table.c.created_at,
        },
    )
