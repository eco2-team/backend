"""
Runtime Settings (FastAPI Official Pattern)

환경변수 기반 동적 설정 - 배포 환경별로 변경됨
Reference: https://fastapi.tiangolo.com/advanced/settings/
"""

from functools import lru_cache
from typing import Optional

from pydantic import AliasChoices, Field, HttpUrl, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration loaded from environment variables."""

    app_name: str = "Auth API"
    environment: str = "local"
    api_v1_prefix: str = "/api/v1"

    # Destructive schema reset guard
    schema_reset_enabled: bool = False

    # Database
    database_url: str = "postgresql+asyncpg://test:test@localhost:5432/test"

    # Redis
    redis_blacklist_url: str = "redis://localhost:6379/0"
    redis_oauth_state_url: str = "redis://localhost:6379/3"

    # RabbitMQ (for ext-authz local cache sync)
    amqp_url: Optional[str] = None  # e.g., "amqp://guest:guest@localhost:5672/"

    # OAuth
    oauth_state_ttl_seconds: int = 600
    oauth_redirect_template: str = "http://localhost:8000/api/v1/auth/{provider}/callback"

    # JWT
    jwt_secret_key: str = "change-me"
    jwt_private_key_pem: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("AUTH_RSA_PRIVATE_KEY", "JWT_PRIVATE_KEY"),
    )
    jwt_algorithm: str = "HS256"
    jwt_issuer: str = "api.dev.growbin.app/api/v1/auth"
    jwt_audience: str = "api"
    access_token_exp_minutes: int = 60 * 3
    refresh_token_exp_minutes: int = 60 * 24 * 30

    # Frontend / Cookie
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

    @property
    def oauth_failure_redirect_url(self) -> str:
        return f"{self.frontend_url}/login?error=oauth_failed"

    # OAuth Providers
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
    """Return cached Settings instance (FastAPI pattern)."""
    return Settings()
