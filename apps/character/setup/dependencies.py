"""Dependency Injection for FastAPI."""

from typing import Annotated, AsyncIterator

from fastapi import Depends
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from apps.character.application.catalog import GetCatalogQuery
from apps.character.application.catalog.ports import CatalogReader
from apps.character.application.reward import EvaluateRewardCommand
from apps.character.application.reward.ports import CharacterMatcher, OwnershipChecker
from apps.character.infrastructure.persistence_postgres import (
    SqlaCharacterReader,
    SqlaOwnershipChecker,
)
from apps.character.infrastructure.persistence_redis import CachedCatalogReader
from apps.character.setup.database import async_session_factory, get_redis


async def get_db_session() -> AsyncIterator[AsyncSession]:
    """DB 세션을 주입합니다."""
    async with async_session_factory() as session:
        try:
            yield session
        finally:
            await session.close()


async def get_redis_client() -> Redis:
    """Redis 클라이언트를 주입합니다."""
    return await get_redis()


async def get_character_reader(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> SqlaCharacterReader:
    """Character Reader를 주입합니다."""
    return SqlaCharacterReader(session)


async def get_catalog_reader(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    redis: Annotated[Redis, Depends(get_redis_client)],
) -> CatalogReader:
    """캐시된 Catalog Reader를 주입합니다."""
    db_reader = SqlaCharacterReader(session)
    return CachedCatalogReader(db_reader, redis)


async def get_character_matcher(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> CharacterMatcher:
    """Character Matcher를 주입합니다."""
    return SqlaCharacterReader(session)


async def get_ownership_checker(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> OwnershipChecker:
    """Ownership Checker를 주입합니다."""
    return SqlaOwnershipChecker(session)


async def get_catalog_query(
    reader: Annotated[CatalogReader, Depends(get_catalog_reader)],
) -> GetCatalogQuery:
    """GetCatalogQuery를 주입합니다."""
    return GetCatalogQuery(reader)


async def get_evaluate_reward_command(
    matcher: Annotated[CharacterMatcher, Depends(get_character_matcher)],
    checker: Annotated[OwnershipChecker, Depends(get_ownership_checker)],
) -> EvaluateRewardCommand:
    """EvaluateRewardCommand를 주입합니다."""
    return EvaluateRewardCommand(matcher, checker)
