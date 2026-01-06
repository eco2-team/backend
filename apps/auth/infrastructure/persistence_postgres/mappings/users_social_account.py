"""UsersSocialAccount ORM Mapping.

타입 규칙 (Unbounded String 기본 전략):
    - TEXT: 기본 문자열 타입
    - VARCHAR: 표준 규격이 명확한 경우만 사용
        - email: VARCHAR(320) - RFC 5321 표준
"""

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    String,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from apps.auth.infrastructure.persistence_postgres.registry import mapper_registry

users_social_accounts_table = Table(
    "user_social_accounts",
    mapper_registry.metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column(
        "user_id",
        UUID(as_uuid=True),
        ForeignKey("auth.users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    ),
    Column("provider", Text, nullable=False, index=True),
    Column("provider_user_id", Text, nullable=False, index=True),
    Column("email", String(320)),  # RFC 5321
    Column("last_login_at", DateTime(timezone=True)),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    UniqueConstraint("provider", "provider_user_id", name="uq_user_social_accounts_identity"),
    schema="auth",
)


def start_users_social_account_mapper() -> None:
    """UsersSocialAccount 매퍼 시작."""
    from apps.auth.domain.entities.user_social_account import UserSocialAccount

    if hasattr(UserSocialAccount, "__mapper__"):
        return

    mapper_registry.map_imperatively(
        UserSocialAccount,
        users_social_accounts_table,
    )
