"""Application configuration."""

from __future__ import annotations

from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Users API 설정."""

    app_name: str = "Users API"
    environment: str = Field(
        "local",
        validation_alias=AliasChoices("ENVIRONMENT", "ENV"),
    )

    # Database
    database_url: str = Field(
        "postgresql+asyncpg://postgres:postgres@localhost:5432/users",
        validation_alias=AliasChoices("DATABASE_URL", "USERS_DATABASE_URL"),
        description="PostgreSQL connection URL",
    )
    database_echo: bool = Field(
        False,
        description="Echo SQL statements",
    )

    # Auth (ext-authz bypass for local dev)
    auth_disabled: bool = Field(
        False,
        validation_alias=AliasChoices("AUTH_DISABLED", "USERS_AUTH_DISABLED"),
        description="Bypass auth validation for local development",
    )

    # gRPC Server
    grpc_server_port: int = Field(
        50051,
        validation_alias=AliasChoices("GRPC_SERVER_PORT", "USERS_GRPC_PORT"),
        description="gRPC server port",
    )
    grpc_max_workers: int = Field(
        10,
        description="Maximum gRPC worker threads",
    )

    # RabbitMQ (Celery)
    celery_broker_url: str = Field(
        "amqp://guest:guest@localhost:5672/",
        validation_alias=AliasChoices("CELERY_BROKER_URL", "RABBITMQ_URL"),
        description="Celery broker URL",
    )

    # Default Character (응답용 설정 - 실제 정보는 character 도메인에서 관리)
    # Note: character_worker가 실제 DB 저장 시 character 도메인에서 조회
    default_character_id: str = Field(
        "00000000-0000-0000-0000-000000000001",
        description="Default character ID for response",
    )
    default_character_code: str = Field(
        "char-eco",
        description="Default character code for response",
    )
    default_character_name: str = Field(
        "이코",
        description="Default character name for response",
    )
    default_character_type: str = Field(
        "기본",
        description="Default character type for response",
    )
    default_character_dialog: str = Field(
        "안녕! 나는 이코야!",
        description="Default character dialog for response",
    )

    model_config = SettingsConfigDict(
        env_prefix="USERS_",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """캐시된 Settings 인스턴스를 반환합니다."""
    return Settings()
