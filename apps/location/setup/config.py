"""Location Service Configuration."""

from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Location 서비스 설정."""

    # Service
    service_name: str = "location-api"
    environment: str = "development"

    # Database
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/location"

    # Redis (메트릭 캐시용)
    redis_url: str = "redis://localhost:6379/5"
    metrics_cache_ttl_seconds: int = 60

    # Auth
    auth_disabled: bool = Field(
        False,
        validation_alias=AliasChoices("LOCATION_AUTH_DISABLED"),
    )

    # gRPC Server (Chat Worker 연동용)
    grpc_enabled: bool = Field(
        True,
        description="gRPC 서버 활성화 여부",
    )
    grpc_port: int = Field(
        50051,
        description="gRPC 서버 포트",
    )

    # OpenTelemetry
    otel_enabled: bool = False
    otel_exporter_otlp_endpoint: str = "http://localhost:4317"

    model_config = SettingsConfigDict(
        env_prefix="LOCATION_",
        case_sensitive=False,
        extra="ignore",
        validate_default=True,
    )


@lru_cache
def get_settings() -> Settings:
    """설정 싱글톤을 반환합니다."""
    return Settings()
