"""Dependency Injection.

Clean Architecture의 Composition Root입니다.
모든 의존성을 여기서 조립합니다.
"""

from __future__ import annotations

import redis.asyncio as aioredis

from apps.auth_relay.application.commands.relay_event import RelayEventCommand
from apps.auth_relay.infrastructure.messaging.rabbitmq_publisher import (
    RabbitMQEventPublisher,
)
from apps.auth_relay.infrastructure.persistence_redis.outbox_reader_redis import (
    RedisOutboxReader,
)
from apps.auth_relay.presentation.relay_loop import RelayLoop
from apps.auth_relay.setup.config import get_settings


class Container:
    """의존성 컨테이너.

    모든 의존성을 생성하고 관리합니다.
    Clean Architecture 계층 순서대로 조립합니다.
    """

    def __init__(self) -> None:
        self._settings = get_settings()

        # Infrastructure
        self._redis: aioredis.Redis | None = None
        self._outbox_reader: RedisOutboxReader | None = None
        self._publisher: RabbitMQEventPublisher | None = None

        # Application
        self._relay_command: RelayEventCommand | None = None

        # Presentation
        self._relay_loop: RelayLoop | None = None

    async def init(self) -> None:
        """의존성 초기화."""
        from redis.asyncio.retry import Retry
        from redis.backoff import ExponentialBackoff
        from redis.exceptions import ConnectionError, TimeoutError

        # 1. Infrastructure 생성 (재시도 로직 포함)
        retry = Retry(ExponentialBackoff(), retries=3)
        self._redis = aioredis.from_url(
            self._settings.redis_url,
            decode_responses=True,
            # Health & Keepalive
            health_check_interval=30,
            socket_keepalive=True,
            # Timeouts
            socket_connect_timeout=5.0,
            socket_timeout=5.0,
            # Connection Pool
            max_connections=50,
            # Retry on transient errors
            retry=retry,
            retry_on_error=[ConnectionError, TimeoutError],
        )
        await self._redis.ping()

        self._outbox_reader = RedisOutboxReader(self._redis)
        self._publisher = RabbitMQEventPublisher(self._settings.amqp_url)
        await self._publisher.connect()

        # 2. Application 생성 (Infrastructure 주입)
        self._relay_command = RelayEventCommand(self._publisher)

        # 3. Presentation 생성 (Application 주입)
        self._relay_loop = RelayLoop(
            self._outbox_reader,
            self._relay_command,
            poll_interval=self._settings.poll_interval,
            batch_size=self._settings.batch_size,
        )

    async def close(self) -> None:
        """리소스 정리."""
        if self._publisher:
            await self._publisher.close()
        if self._redis:
            await self._redis.close()

    @property
    def relay_loop(self) -> RelayLoop:
        """Relay Loop."""
        if not self._relay_loop:
            raise RuntimeError("Container not initialized")
        return self._relay_loop
