from functools import lru_cache
from typing import Optional

from pydantic import HttpUrl, field_validator, Field, AliasChoices
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Auth API"
    environment: str = "local"
    api_v1_prefix: str = "/api/v1"
    # Destructive schema reset guard. Keep False unless you need a full reset.
    schema_reset_enabled: bool = False

    # Database connection (required in production, defaults for testing)
    database_url: str = "postgresql+asyncpg://test:test@localhost:5432/test"

    # Redis connections (required in production, defaults for testing)
    redis_blacklist_url: str = "redis://localhost:6379/0"
    redis_oauth_state_url: str = "redis://localhost:6379/3"

    oauth_state_ttl_seconds: int = 600
    oauth_redirect_template: str = "http://localhost:8000/api/v1/auth/{provider}/callback"

    jwt_secret_key: str = "change-me"
    jwt_private_key_pem: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("AUTH_RSA_PRIVATE_KEY", "JWT_PRIVATE_KEY"),
    )
    jwt_algorithm: str = "RS256"
    jwt_issuer: str = "sesacthon-auth"
    jwt_audience: str = "sesacthon-clients"
    access_token_exp_minutes: int = 60 * 3
    refresh_token_exp_minutes: int = 60 * 24 * 30

    # Frontend / Cookie domains
    frontend_url: str = "https://frontend1.dev.growbin.app"
    cookie_domain: Optional[str] = ".dev.growbin.app"

    # Character service integration
    character_api_base_url: str = "http://character-api.character.svc.cluster.local:8000"
    character_default_grant_endpoint: str = "/api/v1/internal/characters/default"
    character_api_timeout_seconds: float = 5.0
    character_api_token: Optional[str] = None
    character_onboarding_enabled: bool = True
    character_onboarding_retry_attempts: int = 3
    character_onboarding_retry_backoff_seconds: float = 0.5

    # OAuth failure redirect
    @property
    def oauth_failure_redirect_url(self) -> str:
        return f"{self.frontend_url}/login?error=oauth_failed"

    kakao_client_id: str = ""
    kakao_client_secret: Optional[str] = None
    kakao_redirect_uri: Optional[HttpUrl] = None

    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: Optional[HttpUrl] = None

    naver_client_id: str = ""
    naver_client_secret: str = ""
    naver_redirect_uri: Optional[HttpUrl] = None

    model_config = SettingsConfigDict(
        env_prefix="AUTH_",
        case_sensitive=False,
        extra="ignore",
        validate_default=True,
    )

    @field_validator(
        "kakao_redirect_uri", "google_redirect_uri", "naver_redirect_uri", mode="before"
    )
    @classmethod
    def _empty_string_to_none(cls, value: Optional[str]):
        if isinstance(value, str) and not value.strip():
            return None
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
