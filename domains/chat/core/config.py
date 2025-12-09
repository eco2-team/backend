from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Chat API"
    auth_disabled: bool = Field(
        False,
        validation_alias=AliasChoices("CHAT_AUTH_DISABLED"),
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
