"""Database session management for Chat."""

from __future__ import annotations

from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from chat.setup.config import get_settings

settings = get_settings()

engine = create_async_engine(
    settings.database_url,
    echo=settings.database_echo,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
    connect_args={"server_settings": {"timezone": "Asia/Seoul"}},
)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency로 사용할 DB 세션을 생성합니다."""
    async with async_session_factory() as session:
        yield session
