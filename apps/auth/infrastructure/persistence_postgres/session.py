"""PostgreSQL Session Management."""

from __future__ import annotations

import os
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def get_async_engine() -> AsyncEngine:
    """AsyncEngine 생성.

    환경변수:
        - AUTH_DATABASE_URL: PostgreSQL 연결 URL
        - DB_POOL_SIZE: 풀 크기 (기본: 5)
        - DB_MAX_OVERFLOW: 최대 오버플로우 (기본: 10)
    """
    database_url = os.getenv("AUTH_DATABASE_URL")
    if not database_url:
        raise ValueError("AUTH_DATABASE_URL environment variable is required")

    pool_size = int(os.getenv("DB_POOL_SIZE", "5"))
    max_overflow = int(os.getenv("DB_MAX_OVERFLOW", "10"))
    pool_recycle = int(os.getenv("DB_POOL_RECYCLE", "1800"))

    return create_async_engine(
        database_url,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_recycle=pool_recycle,
        pool_pre_ping=True,
        echo=os.getenv("DB_ECHO", "false").lower() == "true",
        connect_args={"options": "-c timezone=Asia/Seoul"},
    )


_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _get_session_factory() -> async_sessionmaker[AsyncSession]:
    """세션 팩토리 싱글톤."""
    global _engine, _session_factory
    if _session_factory is None:
        _engine = get_async_engine()
        _session_factory = async_sessionmaker(
            _engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )
    return _session_factory


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI Depends용 세션 제공자."""
    session_factory = _get_session_factory()
    async with session_factory() as session:
        yield session
