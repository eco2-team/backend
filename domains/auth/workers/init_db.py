"""Initialize database tables for auth service."""

from __future__ import annotations

import asyncio
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from domains.auth.setup.config import get_settings
from domains.auth.infrastructure.database.base import Base
from domains.auth.domain.models.login_audit import LoginAudit  # noqa: F401
from domains.auth.domain.models.user import User  # noqa: F401
from domains.auth.domain.models.user_social_account import UserSocialAccount  # noqa: F401


async def init_db() -> int:
    """Create all database tables."""
    settings = get_settings()
    drop_schema = settings.schema_reset_enabled
    print(
        "🔗 Connecting to database: "
        f"{settings.database_url.split('@')[1] if '@' in settings.database_url else 'database'}"
    )
    if drop_schema:
        print("⚠️  AUTH_SCHEMA_RESET_ENABLED is true → full schema reset allowed.")
    else:
        print("🛡️  Schema reset guard is active → skipping DROP SCHEMA.")

    engine = create_async_engine(settings.database_url, echo=False)

    try:
        async with engine.begin() as conn:
            if drop_schema:
                print("♻️  Dropping existing 'auth' schema (if present)...")
                await conn.execute(text("DROP SCHEMA IF EXISTS auth CASCADE"))
                print("📦 Creating 'auth' schema...")
                await conn.execute(text("CREATE SCHEMA auth"))
            else:
                await conn.execute(text("CREATE SCHEMA IF NOT EXISTS auth"))

            print("📦 Creating database tables...")
            await conn.run_sync(Base.metadata.create_all)

        print("✅ Database tables created successfully!\n")
        print("📋 Created tables:")
        print("   - auth.users")
        print("   - auth.login_audits")
        return 0
    except Exception as exc:  # pragma: no cover - diagnostic output
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
