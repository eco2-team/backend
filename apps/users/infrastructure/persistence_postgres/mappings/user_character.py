"""UserCharacter ORM mapping - Imperative mapping for users.user_characters table.

타입 규칙 (Unbounded String 기본 전략):
    - status: ENUM - 고정 값 (owned, burned, traded)
    - TEXT: 기본 문자열 타입 (character_*, source 등)
    - PostgreSQL에서 VARCHAR와 TEXT는 성능 동일
"""

from __future__ import annotations

from sqlalchemy import Column, DateTime, Table, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import registry

from apps.users.domain.entities.user_character import UserCharacter
from apps.users.domain.enums import UserCharacterStatus
from apps.users.infrastructure.persistence_postgres.constants import USER_CHARACTERS_TABLE
from apps.users.infrastructure.persistence_postgres.mappings.user import metadata

mapper_registry = registry(metadata=metadata)

# users.user_characters 테이블 정의
user_characters_table = Table(
    USER_CHARACTERS_TABLE,
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("user_id", UUID(as_uuid=True), nullable=False, index=True),
    Column("character_id", UUID(as_uuid=True), nullable=False, index=True),
    Column("character_code", Text, nullable=False),
    Column("character_name", Text, nullable=False),
    Column("character_type", Text, nullable=True),
    Column("character_dialog", Text, nullable=True),
    Column("source", Text, nullable=True),
    Column(
        "status",
        Text,  # domains와 호환: String(20)으로 저장됨
        nullable=False,
        default=UserCharacterStatus.OWNED.value,  # "owned"
    ),
    Column("acquired_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column(
        "updated_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    ),
)


def start_user_character_mapper() -> None:
    """UserCharacter 엔티티를 users.user_characters 테이블에 매핑합니다."""
    mapper_registry.map_imperatively(
        UserCharacter,
        user_characters_table,
        properties={
            "id": user_characters_table.c.id,
            "user_id": user_characters_table.c.user_id,
            "character_id": user_characters_table.c.character_id,
            "character_code": user_characters_table.c.character_code,
            "character_name": user_characters_table.c.character_name,
            "character_type": user_characters_table.c.character_type,
            "character_dialog": user_characters_table.c.character_dialog,
            "source": user_characters_table.c.source,
            "status": user_characters_table.c.status,
            "acquired_at": user_characters_table.c.acquired_at,
            "updated_at": user_characters_table.c.updated_at,
        },
    )
