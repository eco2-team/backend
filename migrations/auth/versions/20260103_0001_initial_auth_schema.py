"""Initial auth schema.

Revision ID: 0001
Revises: None
Create Date: 2026-01-03

Auth Domain Migration
Schema: auth.*

Note: DEPRECATED - users 스키마로 통합 진행 중
이 마이그레이션은 롤백 및 레거시 호환성을 위해 유지됩니다.
"""

from typing import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create auth schema tables.

    Note: IF NOT EXISTS로 기존 테이블 보존
    """
    # 스키마 생성
    op.execute("CREATE SCHEMA IF NOT EXISTS auth")

    # ============================================
    # auth.users 테이블
    # ============================================
    op.execute("""
        CREATE TABLE IF NOT EXISTS auth.users (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            username TEXT,
            nickname TEXT,
            profile_image_url TEXT,
            phone_number VARCHAR(20),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            last_login_at TIMESTAMPTZ,

            CONSTRAINT uq_auth_users_name_phone UNIQUE (username, phone_number)
        )
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_auth_users_phone
        ON auth.users(phone_number) WHERE phone_number IS NOT NULL
    """)

    # ============================================
    # auth.user_social_accounts 테이블
    # ============================================
    op.execute("""
        CREATE TABLE IF NOT EXISTS auth.user_social_accounts (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL,
            provider TEXT NOT NULL,
            provider_user_id TEXT NOT NULL,
            email VARCHAR(320),
            last_login_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

            CONSTRAINT fk_auth_social_user
                FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE,
            CONSTRAINT uq_user_social_accounts_identity
                UNIQUE (provider, provider_user_id)
        )
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_auth_social_user_id
        ON auth.user_social_accounts(user_id)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_auth_social_provider
        ON auth.user_social_accounts(provider)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_auth_social_provider_user
        ON auth.user_social_accounts(provider_user_id)
    """)

    # ============================================
    # auth.login_audits 테이블
    # ============================================
    op.execute("""
        CREATE TABLE IF NOT EXISTS auth.login_audits (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL,
            provider TEXT NOT NULL,
            jti TEXT NOT NULL,
            login_ip TEXT,
            user_agent TEXT,
            issued_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

            CONSTRAINT fk_audit_user
                FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE
        )
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_login_audits_user_id
        ON auth.login_audits(user_id)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_login_audits_jti
        ON auth.login_audits(jti)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_login_audits_issued_at
        ON auth.login_audits(issued_at)
    """)


def downgrade() -> None:
    """Drop auth schema.

    주의: 모든 데이터가 삭제됩니다!
    """
    op.execute("DROP TABLE IF EXISTS auth.login_audits CASCADE")
    op.execute("DROP TABLE IF EXISTS auth.user_social_accounts CASCADE")
    op.execute("DROP TABLE IF EXISTS auth.users CASCADE")
    op.execute("DROP SCHEMA IF EXISTS auth CASCADE")
