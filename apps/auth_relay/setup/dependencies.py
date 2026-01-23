"""Dependency Injection.

Clean Architecture의 Composition Root입니다.
모든 의존성을 여기서 조립합니다.
"""

from __future__ import annotations

import logging
import os

import redis.asyncio as aioredis

from auth_relay.application.commands.relay_event import RelayEventCommand
from auth_relay.infrastructure.messaging.rabbitmq_publisher import (
    RabbitMQEventPublisher,
)
from auth_relay.infrastructure.persistence_redis.outbox_reader_redis import (
    RedisOutboxReader,
)
from auth_relay.presentation.relay_loop import RelayLoop
from auth_relay.setup.config import get_settings

_logger = logging.getLogger(__name__)

OTEL_ENABLED = os.getenv("OTEL_ENABLED", "true").lower() == "true"


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

    def _setup_aio_pika_tracing(self) -> None:
        """aio-pika 분산 추적 설정."""
        if not OTEL_ENABLED:
            _logger.info("aio-pika tracing disabled (OTEL_ENABLED=false)")
            return

        try:
            from opentelemetry import trace
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
                OTLPSpanExporter,
            )
            from opentelemetry.instrumentation.aio_pika import AioPikaInstrumentor
            from opentelemetry.sdk.resources import Resource
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.trace.export import BatchSpanProcessor

            resource = Resource.create(
                {
                    "service.name": "auth-relay",
                    "service.version": os.getenv("SERVICE_VERSION", "1.0.0"),
                    "deployment.environment": get_settings().environment,
                    "messaging.system": "rabbitmq",
                }
            )

            provider = TracerProvider(resource=resource)
            endpoint = os.getenv(
                "OTEL_EXPORTER_OTLP_ENDPOINT",
                "http://jaeger-collector-clusterip.istio-system.svc.cluster.local:4318",
            )
            exporter = OTLPSpanExporter(endpoint=f"{endpoint}/v1/traces")
            provider.add_span_processor(BatchSpanProcessor(exporter))
            trace.set_tracer_provider(provider)

            AioPikaInstrumentor().instrument()
            _logger.info(
                "aio-pika tracing enabled",
                extra={"endpoint": endpoint, "service_name": "auth-relay"},
            )

        except ImportError as e:
            _logger.warning(f"aio-pika tracing not available: {e}")
        except Exception as e:
            _logger.error(f"Failed to setup aio-pika tracing: {e}")

    async def init(self) -> None:
        """의존성 초기화."""
        from redis.asyncio.retry import Retry
        from redis.backoff import ExponentialBackoff
        from redis.exceptions import ConnectionError, TimeoutError

        # 0. OpenTelemetry aio-pika 트레이싱 설정
        self._setup_aio_pika_tracing()

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
