"""
Reset the My service user table for development environments.

The script drops `user_profile.users` (if it exists) and recreates it using the latest ORM
definition so that breaking schema changes can be rolled out quickly.
"""

from __future__ import annotations

import asyncio
import sys

from sqlalchemy.ext.asyncio import create_async_engine

from domains.my.core.config import get_settings
from domains.my.models import User


async def reset_user_data() -> int:
    """Drop and recreate the My service user table."""
    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=False)

    print("⚠️  Resetting My service user table (development only)...")
    try:
        async with engine.begin() as conn:
            await conn.run_sync(User.__table__.drop, checkfirst=True)
            await conn.run_sync(User.__table__.create)
        print("✅ My service user table recreated successfully.")
        return 0
    except Exception as exc:  # pragma: no cover - diagnostic output
        import traceback

        print(f"❌ Failed to reset My service user table: {exc}")
        traceback.print_exc()
        return 1
    finally:
        await engine.dispose()


def main() -> None:
    """CLI entrypoint."""
    sys.exit(asyncio.run(reset_user_data()))


if __name__ == "__main__":
    main()
