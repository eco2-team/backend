from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Chat API"
    auth_disabled: bool = Field(
        False,
        validation_alias=AliasChoices("CHAT_AUTH_DISABLED"),
    )
    access_cookie_name: str = Field(
        "s_access",
        validation_alias=AliasChoices("CHAT_ACCESS_COOKIE_NAME", "AUTH_ACCESS_COOKIE_NAME"),
    )
    jwt_secret_key: str = Field(
        "change-me",
        validation_alias=AliasChoices("CHAT_JWT_SECRET_KEY", "AUTH_JWT_SECRET_KEY"),
    )
    jwt_algorithm: str = Field(
        "HS256",
        validation_alias=AliasChoices("CHAT_JWT_ALGORITHM", "AUTH_JWT_ALGORITHM"),
    )
    jwt_issuer: str = Field(
        "sesacthon-auth",
        validation_alias=AliasChoices("CHAT_JWT_ISSUER", "AUTH_JWT_ISSUER"),
    )
    jwt_audience: str = Field(
        "sesacthon-clients",
        validation_alias=AliasChoices("CHAT_JWT_AUDIENCE", "AUTH_JWT_AUDIENCE"),
    )

    model_config = SettingsConfigDict(
        env_prefix="CHAT_",
        case_sensitive=False,
        extra="ignore",
        validate_default=True,
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
