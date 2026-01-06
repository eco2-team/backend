"""Dependency Injection for FastAPI.

Architecture:
    - 로컬 인메모리 캐시 사용 (Redis 의존성 제거)
    - MQ broadcast로 다중 인스턴스 간 캐시 동기화
"""

from typing import Annotated, AsyncIterator

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from character.application.catalog import GetCatalogQuery
from character.application.catalog.ports import CatalogReader
from character.application.catalog.services.catalog_service import CatalogService
from character.application.reward import EvaluateRewardCommand
from character.application.reward.ports import CharacterMatcher, OwnershipChecker
from character.application.reward.services.reward_policy_service import (
    RewardPolicyService,
)
from character.infrastructure.cache import LocalCachedCatalogReader
from character.infrastructure.persistence_postgres import (
    SqlaCharacterReader,
    SqlaOwnershipChecker,
)
from character.setup.database import async_session_factory


async def get_db_session() -> AsyncIterator[AsyncSession]:
    """DB 세션을 주입합니다."""
    async with async_session_factory() as session:
        try:
            yield session
        finally:
            await session.close()


async def get_character_reader(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> SqlaCharacterReader:
    """Character Reader를 주입합니다."""
    return SqlaCharacterReader(session)


async def get_catalog_reader(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> CatalogReader:
    """로컬 캐시된 Catalog Reader를 주입합니다.

    로컬 인메모리 캐시를 사용하여 Redis 의존성 없이
    빠른 응답을 제공합니다. 캐시 miss 시 DB fallback.
    """
    db_reader = SqlaCharacterReader(session)
    return LocalCachedCatalogReader(db_reader)


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


async def get_catalog_service() -> CatalogService:
    """CatalogService를 주입합니다."""
    return CatalogService()


async def get_catalog_query(
    reader: Annotated[CatalogReader, Depends(get_catalog_reader)],
    service: Annotated[CatalogService, Depends(get_catalog_service)],
) -> GetCatalogQuery:
    """GetCatalogQuery를 주입합니다."""
    return GetCatalogQuery(reader, service)


async def get_reward_policy_service() -> RewardPolicyService:
    """RewardPolicyService를 주입합니다."""
    return RewardPolicyService()


async def get_evaluate_reward_command(
    matcher: Annotated[CharacterMatcher, Depends(get_character_matcher)],
    checker: Annotated[OwnershipChecker, Depends(get_ownership_checker)],
    policy: Annotated[RewardPolicyService, Depends(get_reward_policy_service)],
) -> EvaluateRewardCommand:
    """EvaluateRewardCommand를 주입합니다."""
    return EvaluateRewardCommand(matcher, checker, policy)
