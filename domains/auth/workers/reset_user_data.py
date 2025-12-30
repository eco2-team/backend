"""
Reset auth domain user tables for development environments.

Drops the entire `auth` schema and recreates all ORM-managed tables so that
schema changes can be rolled out without manual data migrations.
"""

from __future__ import annotations

import asyncio
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from domains.auth.setup.config import get_settings
from domains.auth.infrastructure.database.base import Base

# Import models so that SQLAlchemy metadata knows about all tables.
from domains.auth.domain.models.login_audit import LoginAudit  # noqa: F401
from domains.auth.domain.models.user import User  # noqa: F401
from domains.auth.domain.models.user_social_account import UserSocialAccount  # noqa: F401


async def reset_user_data() -> int:
    """Drop and recreate the entire auth schema."""
    settings = get_settings()
    if not settings.schema_reset_enabled:
        print(
            "🛡️  Schema reset guard is active. "
            "Set AUTH_SCHEMA_RESET_ENABLED=true only when a destructive reset is required."
        )
        return 0

    engine = create_async_engine(settings.database_url, echo=False)

    print("⚠️  Resetting auth schema (development only)...")
    try:
        async with engine.begin() as conn:
            await conn.execute(text("DROP SCHEMA IF EXISTS auth CASCADE"))
            await conn.execute(text("CREATE SCHEMA auth"))
            await conn.run_sync(Base.metadata.create_all)
        print("✅ Auth schema recreated successfully.")
        return 0
    except Exception as exc:  # pragma: no cover - diagnostic output
        import traceback

        print(f"❌ Failed to reset auth schema: {exc}")
        traceback.print_exc()
        return 1
    finally:
        await engine.dispose()


def main() -> None:
    """CLI entrypoint."""
    sys.exit(asyncio.run(reset_user_data()))


if __name__ == "__main__":
    main()
