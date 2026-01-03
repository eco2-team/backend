"""Database Setup for Worker."""

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker

from apps.character_worker.setup.config import get_settings

settings = get_settings()

# Sync Engine (for Celery worker_process_init)
sync_engine = create_engine(
    settings.database_url,
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,
)

# Sync Session Factory
sync_session_factory = sessionmaker(
    sync_engine,
    class_=Session,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

# Async Engine (for batch task execution)
async_engine = create_async_engine(
    settings.async_database_url,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
)

# Async Session Factory
async_session_factory = async_sessionmaker(
    async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)
