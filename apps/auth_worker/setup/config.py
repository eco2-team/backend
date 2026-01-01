"""Configuration.

환경 변수 기반 설정입니다.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache


@dataclass(frozen=True)
class Settings:
    """워커 설정.

    환경 변수에서 로드됩니다.
    """

    # Redis
    redis_url: str

    # RabbitMQ
    amqp_url: str

    # Logging
    log_level: str = "INFO"

    # Worker
    service_name: str = "auth-worker"
    service_version: str = "1.0.0"
    environment: str = "dev"


@lru_cache
def get_settings() -> Settings:
    """설정 싱글톤 반환."""
    return Settings(
        redis_url=os.environ["AUTH_REDIS_URL"],
        amqp_url=os.environ["AUTH_AMQP_URL"],
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        service_name=os.getenv("SERVICE_NAME", "auth-worker"),
        service_version=os.getenv("SERVICE_VERSION", "1.0.0"),
        environment=os.getenv("ENVIRONMENT", "dev"),
    )
