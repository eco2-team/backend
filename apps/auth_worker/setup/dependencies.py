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

분산 트레이싱 통합:
- aio-pika Instrumentation으로 MQ 메시지 추적
- Jaeger/Kiali에서 API → MQ → Worker 흐름 추적 가능
"""

from __future__ import annotations

import logging
import os

import redis.asyncio as aioredis

_logger = logging.getLogger(__name__)

# OpenTelemetry 활성화 여부
OTEL_ENABLED = os.getenv("OTEL_ENABLED", "true").lower() == "true"

from auth_worker.application.blacklist.commands.persist import (
    PersistBlacklistCommand,
)
from auth_worker.infrastructure.messaging.rabbitmq_client import RabbitMQClient
from auth_worker.infrastructure.persistence_redis.blacklist_store_redis import (
    RedisBlacklistStore,
)
from auth_worker.presentation.adapters.consumer_adapter import ConsumerAdapter
from auth_worker.presentation.handlers.blacklist_handler import BlacklistHandler
from auth_worker.setup.config import get_settings


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

            # TracerProvider 설정
            resource = Resource.create(
                {
                    "service.name": "auth-worker",
                    "service.version": os.getenv("SERVICE_VERSION", "1.0.0"),
                    "deployment.environment": self._settings.environment,
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

            # aio-pika Instrumentation
            AioPikaInstrumentor().instrument()
            _logger.info(
                "aio-pika tracing enabled",
                extra={"endpoint": endpoint, "service_name": "auth-worker"},
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
