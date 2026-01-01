"""Dependency Injection.

Clean Architecture의 Composition Root입니다.
모든 의존성을 여기서 조립합니다.

블로그 참고: https://rooftopsnow.tistory.com/126

main.py (Composition Root)
    │
    ├── Infrastructure 생성
    │     ├── RabbitMQClient (MQ 연결)
    │     └── RedisBlacklistStore (저장소)
    │
    ├── Application 생성
    │     └── PersistBlacklistCommand (Use Case)
    │
    └── Presentation 생성
          ├── BlacklistHandler (메시지 → Command)
          └── ConsumerAdapter (디스패칭 + ack/nack)
"""

from __future__ import annotations

import redis.asyncio as aioredis

from apps.auth_worker.application.commands.persist_blacklist import (
    PersistBlacklistCommand,
)
from apps.auth_worker.infrastructure.messaging.rabbitmq_client import RabbitMQClient
from apps.auth_worker.infrastructure.persistence_redis.blacklist_store_redis import (
    RedisBlacklistStore,
)
from apps.auth_worker.presentation.adapters.consumer_adapter import ConsumerAdapter
from apps.auth_worker.presentation.handlers.blacklist_handler import BlacklistHandler
from apps.auth_worker.setup.config import get_settings


class Container:
    """의존성 컨테이너.

    모든 의존성을 생성하고 관리합니다.
    Clean Architecture 계층 순서대로 조립합니다.
    """

    def __init__(self) -> None:
        self._settings = get_settings()

        # Infrastructure
        self._redis: aioredis.Redis | None = None
        self._rabbitmq_client: RabbitMQClient | None = None
        self._blacklist_store: RedisBlacklistStore | None = None

        # Application
        self._persist_command: PersistBlacklistCommand | None = None

        # Presentation
        self._handler: BlacklistHandler | None = None
        self._consumer_adapter: ConsumerAdapter | None = None

    async def init(self) -> None:
        """의존성 초기화."""
        # 1. Infrastructure 생성
        self._redis = aioredis.from_url(
            self._settings.redis_url,
            decode_responses=True,
        )
        await self._redis.ping()

        self._blacklist_store = RedisBlacklistStore(self._redis)
        self._rabbitmq_client = RabbitMQClient(self._settings.amqp_url)

        # 2. Application 생성 (Infrastructure 주입)
        self._persist_command = PersistBlacklistCommand(self._blacklist_store)

        # 3. Presentation 생성 (Application 주입)
        self._handler = BlacklistHandler(self._persist_command)
        self._consumer_adapter = ConsumerAdapter(self._handler)

    async def close(self) -> None:
        """리소스 정리."""
        if self._rabbitmq_client:
            await self._rabbitmq_client.close()
        if self._redis:
            await self._redis.close()

    @property
    def rabbitmq_client(self) -> RabbitMQClient:
        """RabbitMQ Client."""
        if not self._rabbitmq_client:
            raise RuntimeError("Container not initialized")
        return self._rabbitmq_client

    @property
    def consumer_adapter(self) -> ConsumerAdapter:
        """Consumer Adapter."""
        if not self._consumer_adapter:
            raise RuntimeError("Container not initialized")
        return self._consumer_adapter

    @property
    def persist_command(self) -> PersistBlacklistCommand:
        """블랙리스트 저장 Command (테스트용)."""
        if not self._persist_command:
            raise RuntimeError("Container not initialized")
        return self._persist_command
