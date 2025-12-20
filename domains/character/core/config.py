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

    # === Circuit Breaker Settings ===
    circuit_fail_max: int = Field(
        5,
        ge=1,
        le=20,
        validation_alias=AliasChoices("CHARACTER_CIRCUIT_FAIL_MAX"),
        description="Number of consecutive failures before opening the circuit.",
    )
    circuit_timeout_duration: int = Field(
        30,
        ge=5,
        le=300,
        validation_alias=AliasChoices("CHARACTER_CIRCUIT_TIMEOUT_DURATION"),
        description="Seconds to wait before attempting recovery (half-open state).",
    )

    # === Redis Cache Settings ===
    redis_url: str = Field(
        "redis://localhost:6379/0",
        validation_alias=AliasChoices("CHARACTER_REDIS_URL"),
        description="Redis connection URL for caching.",
    )
    cache_enabled: bool = Field(
        True,
        validation_alias=AliasChoices("CHARACTER_CACHE_ENABLED"),
        description="Enable/disable caching layer.",
    )
    cache_ttl_seconds: int = Field(
        300,  # 5 minutes
        ge=60,
        le=3600,
        validation_alias=AliasChoices("CHARACTER_CACHE_TTL_SECONDS"),
        description="Default cache TTL in seconds.",
    )

    # === CORS Settings ===
    cors_origins: list[str] = Field(
        default=[
            "https://frontend1.dev.growbin.app",
            "https://frontend2.dev.growbin.app",
            "https://frontend.dev.growbin.app",
            "http://localhost:5173",
            "https://localhost:5173",
        ],
        description="Allowed CORS origins. Set via JSON array or comma-separated string.",
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
