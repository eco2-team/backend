from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Location API"
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/location"
    redis_url: str = "redis://localhost:6379/5"
    metrics_cache_ttl_seconds: int = 60
    jwt_secret_key: str = Field(
        "change-me",
        validation_alias=AliasChoices("LOCATION_JWT_SECRET_KEY", "AUTH_JWT_SECRET_KEY"),
    )
    jwt_algorithm: str = Field(
        "HS256",
        validation_alias=AliasChoices("LOCATION_JWT_ALGORITHM", "AUTH_JWT_ALGORITHM"),
    )
    jwt_issuer: str = Field(
        "sesacthon-auth",
        validation_alias=AliasChoices("LOCATION_JWT_ISSUER", "AUTH_JWT_ISSUER"),
    )
    jwt_audience: str = Field(
        "sesacthon-clients",
        validation_alias=AliasChoices("LOCATION_JWT_AUDIENCE", "AUTH_JWT_AUDIENCE"),
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

