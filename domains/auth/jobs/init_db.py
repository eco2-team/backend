"""Initialize database tables for auth service."""

from __future__ import annotations

import asyncio
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from domains.auth.core.config import get_settings
from domains.auth.database.base import Base
from domains.auth.models.login_audit import LoginAudit  # noqa: F401
from domains.auth.models.user import User  # noqa: F401
from domains.auth.models.user_social_account import UserSocialAccount  # noqa: F401


async def init_db() -> int:
    """Create all database tables."""
    settings = get_settings()
    print(
        "🔗 Connecting to database: "
        f"{settings.database_url.split('@')[1] if '@' in settings.database_url else 'database'}"
    )

    engine = create_async_engine(settings.database_url, echo=False)

    try:
        async with engine.begin() as conn:
            exists = await conn.scalar(
                text(
                    "SELECT 1 FROM information_schema.schemata " "WHERE schema_name = :schema_name"
                ),
                {"schema_name": "auth"},
            )
            if exists:
                print("ℹ️  Schema 'auth' already exists; skipping creation.")
            else:
                print("📦 Creating 'auth' schema...")
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
