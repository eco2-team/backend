"""Table Definitions.

Character 도메인의 SQLAlchemy Table 정의.
ORM 매핑 없이 순수 테이블 스키마만 정의합니다.
"""

from sqlalchemy import Column, DateTime, ForeignKey, String, Table, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from character.infrastructure.persistence_postgres.registry import mapper_registry

# character.characters 테이블
characters_table = Table(
    "characters",
    mapper_registry.metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("code", String(64), unique=True, nullable=False),
    Column("name", Text, nullable=False),
    Column("description", Text, nullable=True),
    Column("type_label", Text, nullable=False),
    Column("dialog", Text, nullable=False),
    Column("match_label", Text, nullable=True, index=True),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
    Column("updated_at", DateTime(timezone=True), server_default=func.now(), onupdate=func.now()),
    schema="character",
)

# character.character_ownerships 테이블
character_ownerships_table = Table(
    "character_ownerships",
    mapper_registry.metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("user_id", UUID(as_uuid=True), nullable=False, index=True),
    Column(
        "character_id",
        UUID(as_uuid=True),
        ForeignKey("character.characters.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    ),
    Column("character_code", String(64), nullable=False, index=True),
    Column("source", Text, nullable=True),
    Column("status", String(20), default="owned"),
    Column("acquired_at", DateTime(timezone=True), server_default=func.now()),
    Column("updated_at", DateTime(timezone=True), server_default=func.now(), onupdate=func.now()),
    UniqueConstraint("user_id", "character_code", name="uq_character_ownership_user_code"),
    schema="character",
)
