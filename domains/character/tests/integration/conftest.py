"""Integration test fixtures using testcontainers.

실제 PostgreSQL과 Redis 컨테이너를 사용합니다.
Docker가 실행 중이어야 합니다.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import pytest

# Add project root to path
project_root = Path(__file__).resolve().parents[4]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Skip if testcontainers not installed
pytest.importorskip("testcontainers")

from testcontainers.postgres import PostgresContainer  # noqa: E402
from testcontainers.redis import RedisContainer  # noqa: E402


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def postgres_container():
    """Start PostgreSQL container for the test session."""
    with PostgresContainer("postgres:15-alpine") as postgres:
        yield postgres


@pytest.fixture(scope="session")
def redis_container():
    """Start Redis container for the test session."""
    with RedisContainer("redis:7-alpine") as redis:
        yield redis


@pytest.fixture(scope="session")
def database_url(postgres_container) -> str:
    """Get async database URL from container."""
    # testcontainers returns sync URL, convert to async
    sync_url = postgres_container.get_connection_url()
    # postgresql://user:pass@host:port/db → postgresql+asyncpg://...
    async_url = sync_url.replace("postgresql://", "postgresql+asyncpg://")
    return async_url


@pytest.fixture(scope="session")
def redis_url(redis_container) -> str:
    """Get Redis URL from container."""
    host = redis_container.get_container_host_ip()
    port = redis_container.get_exposed_port(6379)
    return f"redis://{host}:{port}/0"


@pytest.fixture(scope="session")
def configure_test_env(database_url: str, redis_url: str):
    """Configure environment variables for test session."""
    os.environ["CHARACTER_DATABASE_URL"] = database_url
    os.environ["CHARACTER_REDIS_URL"] = redis_url
    os.environ["CHARACTER_CACHE_ENABLED"] = "true"
    os.environ["OTEL_ENABLED"] = "false"
    os.environ["AUTH_DISABLED"] = "true"
    yield
    # Cleanup
    for key in [
        "CHARACTER_DATABASE_URL",
        "CHARACTER_REDIS_URL",
        "CHARACTER_CACHE_ENABLED",
    ]:
        os.environ.pop(key, None)


@pytest.fixture(scope="session")
async def setup_database(database_url: str, configure_test_env):
    """Create database tables."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    from domains.character.database.base import Base

    engine = create_async_engine(database_url, echo=False)

    async with engine.begin() as conn:
        await conn.execute(text('CREATE SCHEMA IF NOT EXISTS "character"'))
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    await engine.dispose()


@pytest.fixture
async def db_session(setup_database):
    """Create a new database session for each test."""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    async_session_factory = async_sessionmaker(
        bind=setup_database,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session_factory() as session:
        yield session
        await session.rollback()  # Rollback after each test


@pytest.fixture
async def character_service(db_session):
    """Create CharacterService with real database session."""
    from domains.character.services.character import CharacterService

    return CharacterService.create_for_test(session=db_session)


@pytest.fixture
async def seed_characters(db_session):
    """Seed test characters into database."""
    from domains.character.models import Character

    characters = [
        Character(
            code="char-eco",
            name="이코",
            type_label="기본",
            dialog="안녕! 나는 이코야!",
            match_label=None,
        ),
        Character(
            code="char-plastic",
            name="플라봇",
            type_label="플라스틱",
            dialog="플라스틱을 분리해줘서 고마워!",
            match_label="플라스틱",
        ),
        Character(
            code="char-glass",
            name="유리봇",
            type_label="유리",
            dialog="유리는 깨지지 않게 조심히!",
            match_label="유리",
        ),
    ]

    for char in characters:
        db_session.add(char)

    await db_session.commit()

    # Refresh to get IDs
    for char in characters:
        await db_session.refresh(char)

    return characters
