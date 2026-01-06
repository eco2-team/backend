"""Database Setup."""

from contextlib import asynccontextmanager
from typing import AsyncIterator

from redis.asyncio import Redis
from redis.asyncio.retry import Retry
from redis.backoff import ExponentialBackoff
from redis.exceptions import ConnectionError, TimeoutError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from character.setup.config import get_settings

# Redis connection settings (domains 정합성)
HEALTH_CHECK_INTERVAL = 30  # seconds
MAX_CONNECTIONS = 50
SOCKET_CONNECT_TIMEOUT = 5.0  # seconds
SOCKET_TIMEOUT = 5.0  # seconds
RETRY_ON_ERROR = [ConnectionError, TimeoutError]
MAX_RETRIES = 3

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
    """Redis 클라이언트를 반환합니다.

    Retry 설정 (domains 정합성):
    - ExponentialBackoff: 지수 백오프 재시도
    - MAX_RETRIES: 3회 재시도
    - ConnectionError, TimeoutError에서 자동 재시도
    """
    global _redis_client
    if _redis_client is None:
        retry = Retry(ExponentialBackoff(), retries=MAX_RETRIES)
        _redis_client = Redis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
            # Health & Keepalive
            health_check_interval=HEALTH_CHECK_INTERVAL,
            socket_keepalive=True,
            # Timeouts
            socket_connect_timeout=SOCKET_CONNECT_TIMEOUT,
            socket_timeout=SOCKET_TIMEOUT,
            # Connection Pool
            max_connections=MAX_CONNECTIONS,
            # Retry on transient errors
            retry=retry,
            retry_on_error=RETRY_ON_ERROR,
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
