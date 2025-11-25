"""Initialize database schema and extensions for location service."""

from __future__ import annotations

import asyncio
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from domains.location.core.config import get_settings
from domains.location.database.base import Base


async def init_db() -> int:
    """Create schema and tables (extensions must be pre-installed by superuser)."""
    settings = get_settings()
    print(
        "🔗 Connecting to database: "
        f"{settings.database_url.split('@')[1] if '@' in settings.database_url else 'database'}"
    )

    engine = create_async_engine(settings.database_url, echo=False)

    try:
        async with engine.begin() as conn:
            # Check and create schema
            exists = await conn.scalar(
                text("SELECT 1 FROM information_schema.schemata WHERE schema_name = :schema_name"),
                {"schema_name": "location"},
            )
            if exists:
                print("ℹ️  Schema 'location' already exists; skipping creation.")
            else:
                print("📦 Creating 'location' schema...")
                await conn.execute(text("CREATE SCHEMA IF NOT EXISTS location"))

            # Verify required extensions (should be pre-installed by DB admin)
            print("🔍 Verifying required PostgreSQL extensions...")
            for ext in ["cube", "earthdistance"]:
                ext_exists = await conn.scalar(
                    text("SELECT 1 FROM pg_extension WHERE extname = :extname"), {"extname": ext}
                )
                if ext_exists:
                    print(f"   ✅ Extension '{ext}' is installed")
                else:
                    print(
                        f"   ⚠️  Extension '{ext}' not found. "
                        "Please install it manually with superuser privileges:"
                    )
                    print(f"      CREATE EXTENSION IF NOT EXISTS {ext};")

            print("📦 Creating database tables...")
            await conn.run_sync(Base.metadata.create_all)

        print("✅ Database initialization completed!\n")
        print("📋 Created tables:")
        print("   - location.location_normalized_sites")
        return 0
    except Exception as exc:  # pragma: no cover - diagnostic output
        print(f"❌ Error initializing database: {exc}")
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
