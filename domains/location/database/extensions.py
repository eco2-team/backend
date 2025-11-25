from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

GEOSPATIAL_EXTENSIONS = ("cube", "earthdistance")


async def ensure_geospatial_extensions(engine: AsyncEngine) -> None:
    """
    Ensure Postgres geospatial helpers (cube/earthdistance) exist.

    Location queries rely on ll_to_earth/earth_distance, which are provided by
    these extensions.

    Note: In production, these extensions should be pre-installed via
    PostgreSQL initdb scripts (see clusters/{dev,prod}/apps/27-postgresql.yaml).
    This function checks existence first to avoid permission errors.
    """

    async with engine.begin() as conn:
        for extension in GEOSPATIAL_EXTENSIONS:
            # Check if extension already exists
            result = await conn.execute(
                text("SELECT 1 FROM pg_extension WHERE extname = :ext_name"),
                {"ext_name": extension},
            )
            if result.scalar():
                continue

            # Try to create extension (will fail if no superuser permissions)
            try:
                await conn.execute(text(f"CREATE EXTENSION IF NOT EXISTS {extension}"))
            except Exception as e:
                # If extension doesn't exist and we lack permissions,
                # this is a deployment configuration error
                raise RuntimeError(
                    f"Extension '{extension}' not found and cannot be created. "
                    f"Ensure PostgreSQL initdb scripts pre-install this extension. "
                    f"See clusters/{{dev,prod}}/apps/27-postgresql.yaml"
                ) from e
