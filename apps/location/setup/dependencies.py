"""Dependency Injection for FastAPI."""

from typing import Annotated, AsyncIterator

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from location.application.nearby import GetNearbyCentersQuery
from location.application.nearby.ports import LocationReader
from location.infrastructure.persistence_postgres import SqlaLocationReader
from location.setup.database import async_session_factory


async def get_db_session() -> AsyncIterator[AsyncSession]:
    """DB 세션을 주입합니다."""
    async with async_session_factory() as session:
        try:
            yield session
        finally:
            await session.close()


async def get_location_reader(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> LocationReader:
    """Location Reader를 주입합니다."""
    return SqlaLocationReader(session)


async def get_nearby_centers_query(
    reader: Annotated[LocationReader, Depends(get_location_reader)],
) -> GetNearbyCentersQuery:
    """GetNearbyCentersQuery를 주입합니다."""
    return GetNearbyCentersQuery(reader)
