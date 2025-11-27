from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for the Character service."""

    app_name: str = "Character API"
    environment: str = "local"

    database_url: str = Field(
        "postgresql+asyncpg://postgres:postgres@localhost:5432/ecoeco",
        description="PostgreSQL connection string for the shared ecoeco database.",
    )
    database_echo: bool = False

    jwt_secret_key: str = Field(
        "change-me",
        validation_alias=AliasChoices("CHARACTER_JWT_SECRET_KEY", "AUTH_JWT_SECRET_KEY"),
    )
    jwt_algorithm: str = Field(
        "HS256",
        validation_alias=AliasChoices("CHARACTER_JWT_ALGORITHM", "AUTH_JWT_ALGORITHM"),
    )
    jwt_issuer: str = Field(
        "sesacthon-auth",
        validation_alias=AliasChoices("CHARACTER_JWT_ISSUER", "AUTH_JWT_ISSUER"),
    )
    jwt_audience: str = Field(
        "sesacthon-clients",
        validation_alias=AliasChoices("CHARACTER_JWT_AUDIENCE", "AUTH_JWT_AUDIENCE"),
    )

    access_cookie_name: str = Field(
        "s_access",
        validation_alias=AliasChoices("CHARACTER_ACCESS_COOKIE_NAME", "AUTH_ACCESS_COOKIE_NAME"),
    )
    auth_disabled: bool = Field(
        False,
        validation_alias=AliasChoices("CHARACTER_AUTH_DISABLED"),
        description="Skip access-token validation for local/manual testing.",
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
