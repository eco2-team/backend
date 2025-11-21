"""Initial migration: create users and login_audits tables

Revision ID: 001_initial
Revises: 
Create Date: 2025-11-20 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create auth schema
    op.execute("CREATE SCHEMA IF NOT EXISTS auth")

    # Create users table
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("provider_user_id", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("username", sa.String(length=120), nullable=True),
        sa.Column("nickname", sa.String(length=120), nullable=True),
        sa.Column("profile_image_url", sa.String(length=512), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("provider", "provider_user_id", name="uq_users_provider_identifier"),
        schema="auth",
    )

    # Create login_audits table
    op.create_table(
        "login_audits",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("jti", sa.String(length=64), nullable=False),
        sa.Column("login_ip", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.Column(
            "issued_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(["user_id"], ["auth.users.id"], ondelete="CASCADE"),
        schema="auth",
    )

    # Create index on user_id
    op.create_index("ix_auth_login_audits_user_id", "login_audits", ["user_id"], schema="auth")


def downgrade() -> None:
    # Drop index
    op.drop_index("ix_auth_login_audits_user_id", table_name="login_audits", schema="auth")

    # Drop tables
    op.drop_table("login_audits", schema="auth")
    op.drop_table("users", schema="auth")

    # Drop schema
    op.execute("DROP SCHEMA IF EXISTS auth")
