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

    model_config = SettingsConfigDict(
        env_prefix="CHARACTER_",
        case_sensitive=False,
        extra="ignore",
        validate_default=True,
    )


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()
