from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "My API"
    database_url: str = Field(
        "postgresql+asyncpg://postgres:postgres@localhost:5432/my",
        description="SQLAlchemy URL used for the My service database.",
    )
    schema_reset_enabled: bool = Field(
        False,
        validation_alias=AliasChoices("MY_SCHEMA_RESET_ENABLED"),
        description="Allow destructive reset jobs to drop/recreate tables.",
    )
    metrics_cache_ttl_seconds: int = 60
    auth_disabled: bool = Field(
        False,
        validation_alias=AliasChoices("MY_AUTH_DISABLED"),
        description="When true, bypasses access-token validation for local development.",
    )

    model_config = SettingsConfigDict(
        env_prefix="MY_",
        case_sensitive=False,
        extra="ignore",
        validate_default=True,
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
