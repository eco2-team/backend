"""Consumer Dependency Injection.

Event-First Architecture: Redis Streams → PostgreSQL 저장 Consumer의 Composition Root.

Architecture:
    Redis Streams (chat:events:{shard})
        ↓ Consumer Group: chat-persistence
    ChatPersistenceConsumer (Infrastructure)
        ↓ persistence dict
    RedisStreamsConsumerAdapter (Presentation)
        ↓ batch
    MessageSaveHandler (Presentation)
        ↓ DTO
    SaveMessagesCommand (Application)
        ↓
    ChatRepositorySQLA (Infrastructure)
        ↓
    PostgreSQL
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

from chat.application.chat.commands.save_messages import SaveMessagesCommand
from chat.infrastructure.messaging.redis_streams_consumer import ChatPersistenceConsumer
from chat.infrastructure.persistence_postgres.adapters.chat_repository_sqla import (
    ChatRepositorySQLA,
)
from chat.infrastructure.persistence_postgres.session import async_session_factory
from chat.presentation.consumer.handler import MessageSaveHandler
from chat.presentation.consumer.redis_streams_adapter import RedisStreamsConsumerAdapter
from chat.setup.config import get_settings

if TYPE_CHECKING:
    from redis.asyncio import Redis
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class ConsumerContainer:
    """Consumer 의존성 컨테이너.

    Clean Architecture 계층 순서대로 조립:
    1. Infrastructure (Redis, DB)
    2. Application (Command)
    3. Presentation (Handler, Adapter)

    Event-First Architecture:
    - Worker가 done 이벤트에 persistence 데이터 포함
    - Event Router와 별개 Consumer Group으로 독립 소비
    - PostgreSQL에 배치 저장
    """

    def __init__(self) -> None:
        self._settings = get_settings()

        # Infrastructure
        self._redis: Redis | None = None
        self._persistence_consumer: ChatPersistenceConsumer | None = None
        self._session: AsyncSession | None = None

        # Application
        self._save_command: SaveMessagesCommand | None = None

        # Presentation
        self._handler: MessageSaveHandler | None = None
        self._consumer_adapter: RedisStreamsConsumerAdapter | None = None

    async def init(self) -> None:
        """의존성 초기화."""
        import redis.asyncio as redis

        # 1. Infrastructure 생성
        # Redis 연결
        self._redis = redis.from_url(
            self._settings.redis_url,
            decode_responses=False,  # bytes로 받아서 consumer에서 처리
        )

        # Consumer 이름 (Pod별 고유)
        consumer_name = os.environ.get(
            "PERSISTENCE_CONSUMER_NAME",
            f"persistence-worker-{os.getpid()}",
        )

        self._persistence_consumer = ChatPersistenceConsumer(
            redis=self._redis,
            consumer_name=consumer_name,
            block_ms=5000,
            count=100,  # 배치 크기와 일치
        )

        # DB 세션 생성 (장기 세션 - Consumer 전용)
        self._session = async_session_factory()

        # Repository
        repository = ChatRepositorySQLA(self._session)

        # 2. Application 생성
        self._save_command = SaveMessagesCommand(repository)

        # 3. Presentation 생성
        self._handler = MessageSaveHandler(
            command=self._save_command,
            batch_size=100,
            batch_timeout=5.0,
            on_commit=self._commit_session,
        )
        self._consumer_adapter = RedisStreamsConsumerAdapter(
            consumer=self._persistence_consumer,
            handler=self._handler,
            flush_interval=5.0,
        )

        logger.info(
            "Consumer container initialized",
            extra={"consumer_name": consumer_name},
        )

    async def _commit_session(self) -> None:
        """DB 세션 커밋 (배치 성공 후 호출)."""
        if self._session:
            await self._session.commit()
            logger.debug("Session committed")

    async def close(self) -> None:
        """리소스 정리."""
        # Consumer adapter 정리 (잔여 배치 flush)
        if self._consumer_adapter:
            await self._consumer_adapter.stop()

        # Redis 연결 종료
        if self._redis:
            await self._redis.close()

        # DB 세션 종료 (커밋 후)
        if self._session:
            await self._session.commit()
            await self._session.close()

        logger.info("Consumer container closed")

    @property
    def consumer_adapter(self) -> RedisStreamsConsumerAdapter:
        """Consumer Adapter."""
        if not self._consumer_adapter:
            raise RuntimeError("Container not initialized")
        return self._consumer_adapter

    @property
    def session(self) -> "AsyncSession":
        """DB Session (배치 커밋용)."""
        if not self._session:
            raise RuntimeError("Container not initialized")
        return self._session
