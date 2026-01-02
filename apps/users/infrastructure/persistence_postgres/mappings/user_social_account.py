"""UserSocialAccount ORM mapping - Imperative mapping for users.social_accounts table.

통합 스키마:
    - auth.user_social_accounts → users.social_accounts 이동
    - user_id는 users.accounts.id 참조 (FK CASCADE)
    - (provider, provider_user_id) 유니크 제약
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    String,
    Table,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import registry

from apps.users.infrastructure.persistence_postgres.mappings.user import metadata

mapper_registry = registry(metadata=metadata)


@dataclass
class UserSocialAccount:
    """소셜 계정 엔티티."""

    id: UUID | None = None
    user_id: UUID | None = None
    provider: str = ""
    provider_user_id: str = ""
    email: str | None = None
    last_login_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


# users.social_accounts 테이블 정의
social_accounts_table = Table(
    "social_accounts",
    metadata,
    Column("id", PG_UUID(as_uuid=True), primary_key=True),
    Column(
        "user_id",
        PG_UUID(as_uuid=True),
        ForeignKey("users.accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    ),
    Column("provider", String(32), nullable=False, index=True),
    Column("provider_user_id", String(255), nullable=False),
    Column("email", String(320), nullable=True),
    Column("last_login_at", DateTime(timezone=True), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column(
        "updated_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    ),
    UniqueConstraint("provider", "provider_user_id", name="uq_social_identity"),
)


def start_user_social_account_mapper() -> None:
    """UserSocialAccount 엔티티를 users.social_accounts 테이블에 매핑합니다."""
    if hasattr(UserSocialAccount, "__mapper__"):
        return

    mapper_registry.map_imperatively(
        UserSocialAccount,
        social_accounts_table,
        properties={
            "id": social_accounts_table.c.id,
            "user_id": social_accounts_table.c.user_id,
            "provider": social_accounts_table.c.provider,
            "provider_user_id": social_accounts_table.c.provider_user_id,
            "email": social_accounts_table.c.email,
            "last_login_at": social_accounts_table.c.last_login_at,
            "created_at": social_accounts_table.c.created_at,
            "updated_at": social_accounts_table.c.updated_at,
        },
    )


__all__ = [
    "UserSocialAccount",
    "social_accounts_table",
    "start_user_social_account_mapper",
]
