"""Alembic Environment Configuration for Character Domain.

이 파일은 마이그레이션 실행 시 환경을 설정합니다.
- 동기/비동기 마이그레이션 지원
- 환경변수에서 DB URL 로드
- autogenerate 지원 (모델 변경 자동 감지)

Usage:
    # 마이그레이션 생성
    cd migrations/character
    alembic revision --autogenerate -m "add new column"

    # 마이그레이션 실행
    alembic upgrade head

    # 롤백
    alembic downgrade -1

    # 현재 버전 확인
    alembic current
"""

import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

# 프로젝트 루트를 path에 추가 (모델 import용)
# database/character/env.py → backend/
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
sys.path.insert(0, PROJECT_ROOT)

# Alembic Config 객체
config = context.config

# 로깅 설정
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# =============================================================================
# 모델 메타데이터 (autogenerate용)
# Clean Architecture 전환 시 import 경로 변경
# =============================================================================
try:
    # Clean Architecture (apps/) - 우선
    from apps.character.infrastructure.persistence_postgres.models import (
        CharacterModel,
        CharacterOwnershipModel,
    )
    from domains._shared.database.base import Base

    # 메타데이터 등록을 위한 참조
    _ = CharacterModel, CharacterOwnershipModel
except ImportError:
    # Legacy (domains/) - 폴백
    from domains.character.database.base import Base
    from domains.character.models.character import (
        Character,
        CharacterOwnership,
    )

    _ = Character, CharacterOwnership

target_metadata = Base.metadata

# DB URL (환경변수 우선)
DATABASE_URL = os.getenv(
    "CHARACTER_DATABASE_URL",
    os.getenv(
        "DATABASE_URL",
        "postgresql://postgres:postgres@localhost:5432/ecoeco",
    ),
)

# asyncpg URL을 psycopg2로 변환 (Alembic은 동기 드라이버 사용)
if DATABASE_URL.startswith("postgresql+asyncpg://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")


def get_url() -> str:
    """DB URL 반환."""
    return DATABASE_URL


def run_migrations_offline() -> None:
    """오프라인 모드에서 마이그레이션 실행.

    DB 연결 없이 SQL만 생성합니다.
    """
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        # character 스키마만 관리
        include_schemas=True,
        version_table_schema="character",
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """온라인 모드에서 마이그레이션 실행.

    실제 DB에 연결하여 마이그레이션을 실행합니다.
    """
    connectable = create_engine(
        get_url(),
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # character 스키마만 관리
            include_schemas=True,
            version_table_schema="character",
            # autogenerate 설정
            compare_type=True,
            compare_server_default=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
