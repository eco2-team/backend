"""Initial users schema.

Revision ID: 0001
Revises: None
Create Date: 2026-01-03

Users Domain Migration
Schema: users.*

통합 스키마:
- auth.users + user_profile.users → users.accounts
- auth.user_social_accounts → users.social_accounts
- user_profile.user_characters → users.user_characters
"""

from typing import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create users schema tables.

    Note: IF NOT EXISTS로 기존 테이블 보존
    """
    # 스키마 생성
    op.execute("CREATE SCHEMA IF NOT EXISTS users")

    # ENUM 타입 생성
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE oauth_provider AS ENUM ('google', 'kakao', 'naver');
        EXCEPTION
            WHEN duplicate_object THEN NULL;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE user_character_status AS ENUM ('owned', 'burned', 'traded');
        EXCEPTION
            WHEN duplicate_object THEN NULL;
        END $$;
    """)

    # ============================================
    # users.accounts 테이블
    # ============================================
    op.execute("""
        CREATE TABLE IF NOT EXISTS users.accounts (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            nickname TEXT,
            name TEXT,
            email VARCHAR(320),
            phone_number VARCHAR(20),
            profile_image_url TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            last_login_at TIMESTAMPTZ,

            CONSTRAINT uq_accounts_phone UNIQUE (phone_number)
        )
    """)

    # Partial indexes
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_accounts_nickname
        ON users.accounts(nickname) WHERE nickname IS NOT NULL
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_accounts_phone
        ON users.accounts(phone_number) WHERE phone_number IS NOT NULL
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_accounts_email
        ON users.accounts(email) WHERE email IS NOT NULL
    """)

    # ============================================
    # users.social_accounts 테이블
    # ============================================
    op.execute("""
        CREATE TABLE IF NOT EXISTS users.social_accounts (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL,
            provider oauth_provider NOT NULL,
            provider_user_id TEXT NOT NULL,
            email VARCHAR(320),
            last_login_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

            CONSTRAINT fk_social_user
                FOREIGN KEY (user_id) REFERENCES users.accounts(id) ON DELETE CASCADE,
            CONSTRAINT uq_social_identity
                UNIQUE (provider, provider_user_id)
        )
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_social_user_id
        ON users.social_accounts(user_id)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_social_provider
        ON users.social_accounts(provider)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_social_provider_user
        ON users.social_accounts(provider, provider_user_id)
    """)

    # ============================================
    # users.user_characters 테이블
    # ============================================
    op.execute("""
        CREATE TABLE IF NOT EXISTS users.user_characters (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL,
            character_id UUID NOT NULL,
            character_code TEXT NOT NULL,
            character_name TEXT NOT NULL,
            character_type TEXT,
            character_dialog TEXT,
            source TEXT,
            status user_character_status NOT NULL DEFAULT 'owned',
            acquired_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

            CONSTRAINT fk_character_user
                FOREIGN KEY (user_id) REFERENCES users.accounts(id) ON DELETE CASCADE,
            CONSTRAINT uq_user_character
                UNIQUE (user_id, character_code)
        )
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_characters_user_id
        ON users.user_characters(user_id)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_characters_character_id
        ON users.user_characters(character_id)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_characters_code
        ON users.user_characters(character_code)
    """)


def downgrade() -> None:
    """Drop users schema.

    주의: 모든 데이터가 삭제됩니다!
    """
    op.execute("DROP TABLE IF EXISTS users.user_characters CASCADE")
    op.execute("DROP TABLE IF EXISTS users.social_accounts CASCADE")
    op.execute("DROP TABLE IF EXISTS users.accounts CASCADE")
    op.execute("DROP TYPE IF EXISTS user_character_status CASCADE")
    op.execute("DROP TYPE IF EXISTS oauth_provider CASCADE")
    op.execute("DROP SCHEMA IF EXISTS users CASCADE")
