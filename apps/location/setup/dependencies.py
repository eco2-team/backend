"""Dependency Injection for FastAPI."""

from __future__ import annotations

import logging
from typing import Annotated, AsyncIterator

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from location.application.nearby import GetNearbyCentersQuery
from location.application.nearby.ports import LocationReader
from location.application.nearby.queries.get_center_detail import GetCenterDetailQuery
from location.application.nearby.queries.search_by_keyword import SearchByKeywordQuery
from location.application.nearby.queries.suggest_places import SuggestPlacesQuery
from location.application.ports.kakao_local_client import KakaoLocalClientPort
from location.infrastructure.persistence_postgres import SqlaLocationReader
from location.setup.config import get_settings
from location.setup.database import async_session_factory

logger = logging.getLogger(__name__)

_kakao_client: KakaoLocalClientPort | None = None


def get_kakao_client() -> KakaoLocalClientPort | None:
    """Kakao Local Client 싱글톤을 반환합니다."""
    global _kakao_client  # noqa: PLW0603
    if _kakao_client is None:
        settings = get_settings()
        if settings.kakao_rest_api_key:
            from location.infrastructure.integrations.kakao import KakaoLocalHttpClient

            _kakao_client = KakaoLocalHttpClient(
                api_key=settings.kakao_rest_api_key,
                timeout=settings.kakao_api_timeout,
            )
            logger.info("Kakao Local HTTP client created")
        else:
            logger.warning("KAKAO_REST_API_KEY not set, Kakao features disabled")
    return _kakao_client


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


async def get_search_by_keyword_query(
    reader: Annotated[LocationReader, Depends(get_location_reader)],
) -> SearchByKeywordQuery | None:
    """SearchByKeywordQuery를 주입합니다."""
    kakao = get_kakao_client()
    if kakao is None:
        return None
    return SearchByKeywordQuery(location_reader=reader, kakao_client=kakao)


def get_suggest_places_query() -> SuggestPlacesQuery | None:
    """SuggestPlacesQuery를 주입합니다."""
    kakao = get_kakao_client()
    if kakao is None:
        return None
    return SuggestPlacesQuery(kakao_client=kakao)


async def get_center_detail_query(
    reader: Annotated[LocationReader, Depends(get_location_reader)],
) -> GetCenterDetailQuery:
    """GetCenterDetailQuery를 주입합니다."""
    kakao = get_kakao_client()
    return GetCenterDetailQuery(location_reader=reader, kakao_client=kakao)
