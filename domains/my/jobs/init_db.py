"""Initialize database tables for My (User Profile) service."""

from __future__ import annotations

import asyncio
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from domains.my.core.config import get_settings
from domains.my.database.base import Base
from domains.my.models.user import User  # noqa: F401
from domains.my.models.auth_user import AuthUser  # noqa: F401
from domains.my.models.auth_user_social_account import AuthUserSocialAccount  # noqa: F401


async def init_db() -> int:
    """Create all database tables for 'user_profile' schema."""
    settings = get_settings()
    drop_schema = settings.schema_reset_enabled
    # Remove user/password from logs for security
    db_host = settings.database_url.split("@")[1] if "@" in settings.database_url else "database"
    print(f"🔗 Connecting to database: {db_host}")

    if drop_schema:
        print("⚠️  MY_SCHEMA_RESET_ENABLED is true → full schema reset allowed.")
    else:
        print("🛡️  Schema reset guard is active → skipping DROP SCHEMA.")

    engine = create_async_engine(settings.database_url, echo=False)

    try:
        async with engine.begin() as conn:
            if drop_schema:
                print("♻️  Dropping existing 'user_profile' schema (if present)...")
                await conn.execute(text("DROP SCHEMA IF EXISTS user_profile CASCADE"))
                print("📦 Creating 'user_profile' schema...")
                await conn.execute(text("CREATE SCHEMA user_profile"))
            else:
                await conn.execute(text("CREATE SCHEMA IF NOT EXISTS user_profile"))

            print("📦 Creating database tables...")
            await conn.run_sync(Base.metadata.create_all)

        print("✅ Database tables created successfully for 'user_profile' schema!\n")
        return 0
    except Exception as exc:
        print(f"❌ Error creating database tables: {exc}")
        import traceback

        traceback.print_exc()
        return 1
    finally:
        await engine.dispose()


def main() -> None:
    """Entry point for database initialization."""
    exit_code = asyncio.run(init_db())
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
