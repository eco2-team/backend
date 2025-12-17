"""
Runtime Settings (FastAPI Official Pattern)

환경변수 기반 동적 설정 - 배포 환경별로 변경됨
Reference: https://fastapi.tiangolo.com/advanced/settings/
"""

from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for the Location service."""

    app_name: str = "Location API"

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/location"
    redis_url: str = "redis://localhost:6379/5"
    metrics_cache_ttl_seconds: int = 60

    auth_disabled: bool = Field(
        False,
        validation_alias=AliasChoices("LOCATION_AUTH_DISABLED"),
    )

    model_config = SettingsConfigDict(
        env_prefix="LOCATION_",
        case_sensitive=False,
        extra="ignore",
        validate_default=True,
    )


@lru_cache
def get_settings() -> Settings:
    """Return cached Settings instance (FastAPI pattern)."""
    return Settings()
