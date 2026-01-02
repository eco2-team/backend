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

    model_config = SettingsConfigDict(
        env_prefix="USERS_",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """캐시된 Settings 인스턴스를 반환합니다."""
    return Settings()
