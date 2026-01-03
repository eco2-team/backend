"""Database Setup."""

from contextlib import asynccontextmanager
from typing import AsyncIterator

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from apps.character.setup.config import get_settings

settings = get_settings()

# SQLAlchemy Engine
engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
)

# Session Factory
async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

# Redis Client
_redis_client: Redis | None = None


async def get_redis() -> Redis:
    """Redis 클라이언트를 반환합니다."""
    global _redis_client
    if _redis_client is None:
        _redis_client = Redis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
        )
    return _redis_client


async def close_redis() -> None:
    """Redis 연결을 닫습니다."""
    global _redis_client
    if _redis_client is not None:
        await _redis_client.close()
        _redis_client = None


@asynccontextmanager
async def get_session() -> AsyncIterator[AsyncSession]:
    """SQLAlchemy 세션을 반환합니다."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
