"""Configuration settings.

환경변수에서 설정을 로드합니다.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache


@dataclass(frozen=True)
class Settings:
    """Workers 설정."""

    # Database
    database_url: str
    db_pool_size: int = 5
    db_max_overflow: int = 10
    db_pool_timeout: int = 30

    # Celery
    celery_broker_url: str = "amqp://guest:guest@localhost:5672//"
    celery_result_backend: str | None = None

    # Logging
    log_level: str = "INFO"
    log_format: str = "json"

    # Service
    service_name: str = "users-worker"
    environment: str = "dev"


@lru_cache
def get_settings() -> Settings:
    """설정 인스턴스 반환 (캐싱)."""
    return Settings(
        database_url=os.getenv(
            "USERS_DATABASE_URL",
            "postgresql+asyncpg://postgres:postgres@localhost:5432/users",
        ),
        db_pool_size=int(os.getenv("DB_POOL_SIZE", "5")),
        db_max_overflow=int(os.getenv("DB_MAX_OVERFLOW", "10")),
        db_pool_timeout=int(os.getenv("DB_POOL_TIMEOUT", "30")),
        celery_broker_url=os.getenv(
            "CELERY_BROKER_URL",
            "amqp://guest:guest@localhost:5672//",
        ),
        celery_result_backend=os.getenv("CELERY_RESULT_BACKEND"),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        log_format=os.getenv("LOG_FORMAT", "json"),
        service_name=os.getenv("SERVICE_NAME", "users-worker"),
        environment=os.getenv("ENVIRONMENT", "dev"),
    )
