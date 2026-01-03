"""Initial character schema.

Revision ID: 0001
Revises: None
Create Date: 2026-01-01

Character Domain Migration
Schema: character.*

이 마이그레이션은 기존 스키마가 이미 존재한다고 가정합니다.
새 환경에서는 테이블을 생성하고, 기존 환경에서는 스킵됩니다.
"""

from typing import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create initial character schema tables.

    Note: IF NOT EXISTS로 기존 테이블 보존
    """
    # 스키마 생성
    op.execute("CREATE SCHEMA IF NOT EXISTS character")

    # ENUM 타입 생성
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE character.character_ownership_status AS ENUM ('owned', 'burned', 'traded');
        EXCEPTION
            WHEN duplicate_object THEN NULL;
        END $$;
    """)

    # characters 테이블
    op.execute("""
        CREATE TABLE IF NOT EXISTS character.characters (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            code VARCHAR(64) NOT NULL UNIQUE,
            name TEXT NOT NULL,
            description TEXT,
            type_label TEXT NOT NULL,
            dialog TEXT NOT NULL,
            match_label TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    # match_label 인덱스
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_characters_match_label
        ON character.characters(match_label)
    """)

    # character_ownerships 테이블 (character_code 포함 버전)
    op.execute("""
        CREATE TABLE IF NOT EXISTS character.character_ownerships (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL,
            character_id UUID NOT NULL REFERENCES character.characters(id) ON DELETE CASCADE,
            character_code VARCHAR(64) NOT NULL,
            source TEXT,
            status character.character_ownership_status NOT NULL DEFAULT 'owned',
            acquired_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    # 인덱스들
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_character_ownerships_user_id
        ON character.character_ownerships(user_id)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_character_ownerships_character_id
        ON character.character_ownerships(character_id)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_character_ownerships_character_code
        ON character.character_ownerships(character_code)
    """)

    # UNIQUE 제약 (user_id, character_code)
    op.execute("""
        DO $$ BEGIN
            ALTER TABLE character.character_ownerships
            ADD CONSTRAINT uq_character_ownership_user_code
            UNIQUE (user_id, character_code);
        EXCEPTION
            WHEN duplicate_table THEN NULL;
            WHEN duplicate_object THEN NULL;
        END $$;
    """)


def downgrade() -> None:
    """Drop character schema.

    주의: 모든 데이터가 삭제됩니다!
    """
    op.execute("DROP TABLE IF EXISTS character.character_ownerships CASCADE")
    op.execute("DROP TABLE IF EXISTS character.characters CASCADE")
    op.execute("DROP TYPE IF EXISTS character.character_ownership_status CASCADE")
    op.execute("DROP SCHEMA IF EXISTS character CASCADE")
