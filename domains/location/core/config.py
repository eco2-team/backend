from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
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
    return Settings()
