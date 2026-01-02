"""User ORM mapping - Imperative mapping for users.accounts table.

통합 스키마:
    - auth.users + user_profile.users 병합
    - id는 UUID (기존 auth.users.id를 그대로 사용)
    - username 컬럼 제거 (OAuth 전용이므로 불필요)
"""

from __future__ import annotations

from sqlalchemy import Column, DateTime, MetaData, String, Table, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import registry

from apps.users.domain.entities.user import User

# users 스키마용 메타데이터
metadata = MetaData(schema="users")
mapper_registry = registry(metadata=metadata)

# users.accounts 테이블 정의 (통합 스키마)
accounts_table = Table(
    "accounts",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("nickname", String(120), nullable=True),
    Column("name", String(120), nullable=True),
    Column("email", String(320), nullable=True),
    Column("phone_number", String(32), nullable=True, unique=True),
    Column("profile_image_url", String(512), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column(
        "updated_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    ),
    Column("last_login_at", DateTime(timezone=True), nullable=True),
)


def start_user_mapper() -> None:
    """User 엔티티를 users.accounts 테이블에 매핑합니다."""
    mapper_registry.map_imperatively(
        User,
        accounts_table,
        properties={
            "id": accounts_table.c.id,
            "nickname": accounts_table.c.nickname,
            "name": accounts_table.c.name,
            "email": accounts_table.c.email,
            "phone_number": accounts_table.c.phone_number,
            "profile_image_url": accounts_table.c.profile_image_url,
            "created_at": accounts_table.c.created_at,
            "updated_at": accounts_table.c.updated_at,
            "last_login_at": accounts_table.c.last_login_at,
        },
    )
