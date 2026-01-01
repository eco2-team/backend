"""Configuration.

환경 변수 기반 설정입니다.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache


@dataclass(frozen=True)
class Settings:
    """Relay 워커 설정.

    환경 변수에서 로드됩니다.
    """

    # Redis
    redis_url: str

    # RabbitMQ
    amqp_url: str

    # Relay
    poll_interval: float = 1.0
    batch_size: int = 10

    # Logging
    log_level: str = "INFO"

    # Service
    service_name: str = "auth-relay"
    service_version: str = "1.0.0"
    environment: str = "dev"


@lru_cache
def get_settings() -> Settings:
    """설정 싱글톤 반환."""
    return Settings(
        redis_url=os.environ["AUTH_REDIS_URL"],
        amqp_url=os.environ["AUTH_AMQP_URL"],
        poll_interval=float(os.getenv("RELAY_POLL_INTERVAL", "1.0")),
        batch_size=int(os.getenv("RELAY_BATCH_SIZE", "10")),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        service_name=os.getenv("SERVICE_NAME", "auth-relay"),
        service_version=os.getenv("SERVICE_VERSION", "1.0.0"),
        environment=os.getenv("ENVIRONMENT", "dev"),
    )
