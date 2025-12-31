"""User ORM mapping - Imperative mapping for users.users table."""

from __future__ import annotations

from sqlalchemy import BigInteger, Column, DateTime, MetaData, String, Table, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import registry

from apps.users.domain.entities.user import User

# users 스키마용 메타데이터
metadata = MetaData(schema="users")
mapper_registry = registry(metadata=metadata)

# users.users 테이블 정의
users_table = Table(
    "users",
    metadata,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("auth_user_id", UUID(as_uuid=True), nullable=False, unique=True, index=True),
    Column("username", String(120), nullable=True, index=True),
    Column("nickname", String(120), nullable=True),
    Column("name", String(120), nullable=True),
    Column("email", String(320), nullable=True),
    Column("phone_number", String(32), nullable=True, index=True),
    Column("profile_image_url", String(500), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)


def start_user_mapper() -> None:
    """User 엔티티를 users.users 테이블에 매핑합니다."""
    mapper_registry.map_imperatively(
        User,
        users_table,
        properties={
            "id": users_table.c.id,
            "auth_user_id": users_table.c.auth_user_id,
            "username": users_table.c.username,
            "nickname": users_table.c.nickname,
            "name": users_table.c.name,
            "email": users_table.c.email,
            "phone_number": users_table.c.phone_number,
            "profile_image_url": users_table.c.profile_image_url,
            "created_at": users_table.c.created_at,
        },
    )
