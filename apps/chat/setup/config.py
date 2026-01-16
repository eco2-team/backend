"""Chat API Configuration."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Chat API 설정."""

    # Service
    service_name: str = "chat-api"
    environment: str = "local"
    debug: bool = False
    host: str = "0.0.0.0"
    port: int = 8000

    # RabbitMQ (Taskiq)
    rabbitmq_url: str = "amqp://guest:guest@localhost:5672/"

    # Redis Pub/Sub (SSE Gateway)
    # event_router가 발행하는 Pub/Sub 채널 구독용
    redis_pubsub_url: str = "redis://localhost:6379/1"

    # Redis Streams (이벤트 발행용 - Worker 전용)
    redis_url: str = "redis://localhost:6379/0"

    # LLM
    default_provider: Literal["openai", "gemini"] = "openai"
    default_model: str = "gpt-5.2-turbo"

    # CORS
    cors_origins: list[str] = ["*"]

    # Database
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/eco2"
    database_echo: bool = False

    # Logging
    log_level: str = "INFO"

    class Config:
        env_prefix = "CHAT_"
        env_file = ".env"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    """설정 싱글톤."""
    return Settings()
