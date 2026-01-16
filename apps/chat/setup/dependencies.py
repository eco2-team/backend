"""Chat API Dependencies - DI 팩토리.

API의 책임:
- 작업 제출 (Taskiq)
- SSE 스트리밍 (Redis Pub/Sub 구독)
- 채팅/메시지 CRUD (PostgreSQL)

이벤트 발행은 Worker에서 수행
"""

from __future__ import annotations

import logging
from typing import Annotated, AsyncGenerator

from fastapi import Depends
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from chat.application.chat.commands import SubmitChatCommand
from chat.application.chat.ports import JobSubmitterPort
from chat.application.chat.ports.chat_repository import ChatRepositoryPort
from chat.infrastructure.messaging import TaskiqJobSubmitter
from chat.infrastructure.persistence_postgres import async_session_factory
from chat.infrastructure.persistence_postgres.adapters import ChatRepositorySQLA
from chat.setup.config import get_settings

logger = logging.getLogger(__name__)

# Singleton
_job_submitter: JobSubmitterPort | None = None
_async_redis: Redis | None = None


async def get_job_submitter() -> JobSubmitterPort:
    """JobSubmitter 싱글톤."""
    global _job_submitter
    if _job_submitter is None:
        _job_submitter = TaskiqJobSubmitter()
    return _job_submitter


async def get_async_redis() -> Redis:
    """비동기 Redis 클라이언트 싱글톤 (SSE Gateway용).

    event_router가 발행하는 Pub/Sub 채널 구독.
    """
    global _async_redis
    if _async_redis is None:
        settings = get_settings()
        _async_redis = Redis.from_url(
            settings.redis_pubsub_url,
            decode_responses=False,
            socket_timeout=60.0,
            socket_connect_timeout=5.0,
            retry_on_timeout=True,
            health_check_interval=30,
        )
        logger.info("Redis Pub/Sub client initialized: %s", settings.redis_pubsub_url)
    return _async_redis


async def get_submit_command() -> SubmitChatCommand:
    """SubmitChatCommand 팩토리."""
    job_submitter = await get_job_submitter()
    return SubmitChatCommand(job_submitter=job_submitter)


# Type aliases for FastAPI Depends
SubmitCommandDep = Annotated[SubmitChatCommand, Depends(get_submit_command)]


# ============================================================
# Database Session & Repository
# ============================================================


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """DB 세션 팩토리 (요청별 세션)."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_chat_repository(
    session: AsyncSession = Depends(get_db_session),
) -> ChatRepositoryPort:
    """ChatRepository 팩토리."""
    return ChatRepositorySQLA(session)


# Type aliases
DbSessionDep = Annotated[AsyncSession, Depends(get_db_session)]
ChatRepositoryDep = Annotated[ChatRepositoryPort, Depends(get_chat_repository)]


# ============================================================
# Container (Lifecycle)
# ============================================================


class Container:
    """리소스 컨테이너 (라이프사이클 관리)."""

    async def close(self):
        """리소스 정리."""
        global _async_redis, _job_submitter

        if _async_redis:
            await _async_redis.close()
            _async_redis = None
            logger.info("Redis Pub/Sub client closed")

        _job_submitter = None


_container: Container | None = None


def get_container() -> Container:
    """Container 싱글톤."""
    global _container
    if _container is None:
        _container = Container()
    return _container
