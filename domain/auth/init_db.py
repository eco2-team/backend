"""Initialize database tables for auth service."""

import asyncio
import sys
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from domain.auth.core.config import get_settings
from domain.auth.database.base import Base
from domain.auth.models.user import User  # noqa: F401
from domain.auth.models.login_audit import LoginAudit  # noqa: F401


async def init_db():
    """Create all database tables."""
    settings = get_settings()
    print(
        f"🔗 Connecting to database: {settings.database_url.split('@')[1] if '@' in settings.database_url else 'database'}"
    )

    engine = create_async_engine(settings.database_url, echo=False)

    try:
        async with engine.begin() as conn:
            # 1. auth 스키마 생성
            print("📦 Creating 'auth' schema if not exists...")
            await conn.execute(text("CREATE SCHEMA IF NOT EXISTS auth"))

            # 2. 테이블 생성
            print("📦 Creating database tables...")
            await conn.run_sync(Base.metadata.create_all)

        print("✅ Database tables created successfully!")
        print("")
        print("📋 Created tables:")
        print("   - auth.users")
        print("   - auth.login_audits")

        return 0
    except Exception as e:
        print(f"❌ Error creating database tables: {e}")
        import traceback

        traceback.print_exc()
        return 1
    finally:
        await engine.dispose()


def main():
    """Entry point for database initialization."""
    exit_code = asyncio.run(init_db())
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
