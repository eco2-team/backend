"""Chat ORM Mapping - Imperative mapping for chat.conversations table.

대화 세션 테이블 매핑.
사이드바에 표시되는 대화 목록.
"""

from __future__ import annotations

from sqlalchemy import Boolean, Column, DateTime, Integer, Table, Text, func
from sqlalchemy.dialects.postgresql import UUID

from chat.domain.entities.chat import Chat
from chat.infrastructure.persistence_postgres.constants import CONVERSATIONS_TABLE
from chat.infrastructure.persistence_postgres.registry import (
    mapper_registry,
    metadata,
)

# chat.conversations 테이블 정의
conversations_table = Table(
    CONVERSATIONS_TABLE,
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("user_id", UUID(as_uuid=True), nullable=False),
    Column("title", Text, nullable=True),
    Column("preview", Text, nullable=True),
    Column("message_count", Integer, nullable=False, server_default="0"),
    Column("last_message_at", DateTime(timezone=True), nullable=True),
    Column("is_deleted", Boolean, nullable=False, server_default="false"),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column(
        "updated_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    ),
)


def start_chat_mapper() -> None:
    """Chat 엔티티를 chat.conversations 테이블에 매핑합니다."""
    if hasattr(Chat, "__mapper__"):
        return

    mapper_registry.map_imperatively(
        Chat,
        conversations_table,
        properties={
            "id": conversations_table.c.id,
            "user_id": conversations_table.c.user_id,
            "title": conversations_table.c.title,
            "preview": conversations_table.c.preview,
            "message_count": conversations_table.c.message_count,
            "last_message_at": conversations_table.c.last_message_at,
            "is_deleted": conversations_table.c.is_deleted,
            "created_at": conversations_table.c.created_at,
            "updated_at": conversations_table.c.updated_at,
        },
    )
