"""Dependency Injection.

Clean Architecture의 Composition Root입니다.
모든 의존성을 여기서 조립합니다.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import redis.asyncio as aioredis

from apps.auth_worker.application.commands.persist_blacklist import (
    PersistBlacklistCommand,
)
from apps.auth_worker.infrastructure.messaging.rabbitmq_consumer import RabbitMQConsumer
from apps.auth_worker.infrastructure.persistence_redis.blacklist_store_redis import (
    RedisBlacklistStore,
)
from apps.auth_worker.setup.config import get_settings

if TYPE_CHECKING:
    pass


class Container:
    """의존성 컨테이너.

    모든 의존성을 생성하고 관리합니다.
    """

    def __init__(self) -> None:
        self._settings = get_settings()
        self._redis: aioredis.Redis | None = None
        self._consumer: RabbitMQConsumer | None = None
        self._blacklist_store: RedisBlacklistStore | None = None
        self._persist_command: PersistBlacklistCommand | None = None

    async def init(self) -> None:
        """의존성 초기화."""
        # Redis 연결
        self._redis = aioredis.from_url(
            self._settings.redis_url,
            decode_responses=True,
        )
        await self._redis.ping()

        # Infrastructure 생성
        self._blacklist_store = RedisBlacklistStore(self._redis)
        self._consumer = RabbitMQConsumer(self._settings.amqp_url)

        # Application 생성 (DI)
        self._persist_command = PersistBlacklistCommand(self._blacklist_store)

    async def close(self) -> None:
        """리소스 정리."""
        if self._consumer:
            await self._consumer.stop()
        if self._redis:
            await self._redis.close()

    @property
    def consumer(self) -> RabbitMQConsumer:
        """RabbitMQ Consumer."""
        if not self._consumer:
            raise RuntimeError("Container not initialized")
        return self._consumer

    @property
    def persist_command(self) -> PersistBlacklistCommand:
        """블랙리스트 저장 Command."""
        if not self._persist_command:
            raise RuntimeError("Container not initialized")
        return self._persist_command
