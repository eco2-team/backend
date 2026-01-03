"""Alembic Environment Configuration for Auth Domain.

Note: auth 스키마는 DEPRECATED - users 스키마로 통합 진행 중

Usage:
    cd migrations/auth
    alembic revision --autogenerate -m "add new column"
    alembic upgrade head
    alembic downgrade -1
    alembic current
"""

import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

# 프로젝트 루트를 path에 추가
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
sys.path.insert(0, PROJECT_ROOT)

# Alembic Config 객체
config = context.config

# 로깅 설정
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# =============================================================================
# 모델 메타데이터 (autogenerate용)
# =============================================================================
try:
    # Clean Architecture (apps/)
    from apps.auth.infrastructure.persistence_postgres.models import (
        User,
        UserSocialAccount,
        LoginAudit,
    )
    from apps.auth.infrastructure.persistence_postgres.database import Base
except ImportError:
    # Legacy (domains/)
    try:
        from domains.auth.database.base import Base
        from domains.auth.models.user import User, UserSocialAccount
        from domains.auth.models.audit import LoginAudit
    except ImportError:
        # 모델 없이 실행 (SQL만 생성)
        from sqlalchemy.orm import declarative_base
        Base = declarative_base()

target_metadata = Base.metadata

# DB URL (환경변수 우선)
DATABASE_URL = os.getenv(
    "AUTH_DATABASE_URL",
    os.getenv(
        "DATABASE_URL",
        "postgresql://postgres:postgres@localhost:5432/ecoeco",
    ),
)

# asyncpg URL을 psycopg2로 변환
if DATABASE_URL.startswith("postgresql+asyncpg://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")


def get_url() -> str:
    return DATABASE_URL


def run_migrations_offline() -> None:
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_schemas=True,
        version_table_schema="auth",
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(
        get_url(),
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_schemas=True,
            version_table_schema="auth",
            compare_type=True,
            compare_server_default=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
