"""Celery configuration settings.

환경변수를 통해 설정을 관리합니다.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings


class CelerySettings(BaseSettings):
    """Celery configuration from environment variables."""

    # Broker (RabbitMQ)
    broker_url: str = Field(
        default="amqp://guest:guest@localhost:5672//",
        alias="CELERY_BROKER_URL",
        description="RabbitMQ broker URL",
    )

    # Backend (Redis)
    result_backend: str = Field(
        default="redis://localhost:6379/1",
        alias="CELERY_RESULT_BACKEND",
        description="Redis backend for task results and state",
    )

    # Task state Redis (별도 DB 사용 권장)
    state_redis_url: str = Field(
        default="redis://localhost:6379/2",
        alias="CELERY_STATE_REDIS_URL",
        description="Redis URL for task state management",
    )

    # Task settings
    task_serializer: str = Field(default="json")
    result_serializer: str = Field(default="json")
    accept_content: list[str] = Field(default=["json"])
    timezone: str = Field(default="Asia/Seoul")
    enable_utc: bool = Field(default=True)

    # Task execution
    task_acks_late: bool = Field(
        default=True,
        description="Acknowledge task after completion (safer)",
    )
    task_reject_on_worker_lost: bool = Field(
        default=True,
        description="Reject task if worker dies",
    )

    # Result settings
    result_expires: int = Field(
        default=86400,  # 24 hours
        description="Task result expiration in seconds",
    )

    # Worker settings
    worker_prefetch_multiplier: int = Field(
        default=1,
        description="Prefetch count (1 for fair distribution)",
    )
    worker_concurrency: int = Field(
        default=4,
        alias="CELERY_WORKER_CONCURRENCY",
        description="Number of concurrent worker processes",
    )

    # Queue settings
    task_default_queue: str = Field(default="default")
    task_create_missing_queues: bool = Field(default=True)

    # Retry settings
    task_default_retry_delay: int = Field(
        default=60,
        description="Default retry delay in seconds",
    )

    # State TTL
    state_ttl_seconds: int = Field(
        default=86400,  # 24 hours
        alias="CELERY_STATE_TTL",
        description="Task state TTL in Redis",
    )

    model_config = {"env_prefix": "", "extra": "ignore"}


@lru_cache
def get_celery_settings() -> CelerySettings:
    """Get cached Celery settings instance."""
    return CelerySettings()
