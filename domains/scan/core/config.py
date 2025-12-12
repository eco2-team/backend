from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Scan API"
    character_api_base_url: str = Field(
        "http://character-api.character.svc.cluster.local:8000",
        description="Base URL for the Character service (no trailing slash).",
    )
    character_grpc_target: str = Field(
        "character-grpc.character.svc.cluster.local:50051",
        description="gRPC target address for Character service (host:port).",
    )
    character_reward_endpoint: str = Field(
        "/api/v1/internal/characters/rewards",
        description="Path for the character reward evaluation endpoint.",
    )
    character_api_timeout_seconds: float = Field(
        30.0,
        ge=0.1,
        description="Timeout in seconds for Character service HTTP calls.",
    )
    character_api_token: str | None = Field(
        default=None,
        description="Optional bearer token for Character internal API authentication.",
    )
    reward_feature_enabled: bool = True
    auth_disabled: bool = Field(
        False,
        validation_alias=AliasChoices("SCAN_AUTH_DISABLED"),
        description="When true, skips token validation (use only for local dev).",
    )

    model_config = SettingsConfigDict(
        env_prefix="SCAN_",
        case_sensitive=False,
        extra="ignore",
        validate_default=True,
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
