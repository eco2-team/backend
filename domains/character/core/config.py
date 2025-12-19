"""
Runtime Settings (FastAPI Official Pattern)

환경변수 기반 동적 설정 - 배포 환경별로 변경됨
Reference: https://fastapi.tiangolo.com/advanced/settings/
"""

from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for the Character service."""

    app_name: str = "Character API"
    environment: str = "local"

    schema_reset_enabled: bool = Field(
        False,
        validation_alias=AliasChoices("CHARACTER_SCHEMA_RESET_ENABLED"),
        description="Allow destructive schema reset jobs (DROP/CREATE).",
    )
    database_url: str = Field(
        "postgresql+asyncpg://postgres:postgres@localhost:5432/ecoeco",
        description="PostgreSQL connection string for the shared ecoeco database.",
    )
    database_echo: bool = False

    auth_disabled: bool = Field(
        False,
        validation_alias=AliasChoices("CHARACTER_AUTH_DISABLED"),
        description="Skip access-token validation for local/manual testing.",
    )
    service_token_secret: str | None = Field(
        default=None,
        validation_alias=AliasChoices("CHARACTER_SERVICE_TOKEN_SECRET"),
        description="Shared secret used to authorize internal service-to-service calls.",
    )

    # === gRPC Server Settings ===
    # Note: validation_alias 필수 - K8s Service가 GRPC_PORT=tcp://... 형태로 주입하여 충돌
    grpc_server_port: int = Field(
        50051,
        validation_alias=AliasChoices("CHARACTER_GRPC_SERVER_PORT"),
        description="gRPC server listening port.",
    )
    grpc_max_workers: int = Field(
        10,
        ge=1,
        le=100,
        validation_alias=AliasChoices("CHARACTER_GRPC_MAX_WORKERS"),
        description="Maximum number of thread pool workers for gRPC server.",
    )

    # === gRPC Client Settings (for calling My service) ===
    my_grpc_host: str = Field(
        "my-api.my.svc.cluster.local",
        validation_alias=AliasChoices("CHARACTER_MY_GRPC_HOST"),
        description="My service gRPC host.",
    )
    my_grpc_port: int = Field(
        50052,
        validation_alias=AliasChoices("CHARACTER_MY_GRPC_PORT"),
        description="My service gRPC port.",
    )
    grpc_timeout_seconds: float = Field(
        5.0,
        ge=0.1,
        le=60.0,
        description="Default timeout for gRPC calls in seconds.",
    )
    grpc_max_retries: int = Field(
        3,
        ge=0,
        le=10,
        description="Maximum number of retry attempts for transient gRPC failures.",
    )
    grpc_retry_base_delay: float = Field(
        0.1,
        ge=0.01,
        le=5.0,
        description="Base delay in seconds for exponential backoff retry.",
    )
    grpc_retry_max_delay: float = Field(
        2.0,
        ge=0.1,
        le=30.0,
        description="Maximum delay in seconds for exponential backoff retry.",
    )

    model_config = SettingsConfigDict(
        env_prefix="CHARACTER_",
        case_sensitive=False,
        extra="ignore",
        validate_default=True,
    )


@lru_cache
def get_settings() -> Settings:
    """Return cached Settings instance (FastAPI pattern)."""
    return Settings()
