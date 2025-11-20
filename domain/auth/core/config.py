from functools import lru_cache
from typing import Optional

from pydantic import HttpUrl, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Auth API"
    environment: str = "local"
    api_v1_prefix: str = "/api/v1"

    database_url: str = (
        "postgresql+asyncpg://sesacthon:sesacthon@postgres-cluster.postgres.svc.cluster.local:5432/sesacthon"
    )

    redis_blacklist_url: str = "redis://redis-cluster.redis.svc.cluster.local:6379/0"
    redis_oauth_state_url: str = "redis://redis-cluster.redis.svc.cluster.local:6379/3"

    oauth_state_ttl_seconds: int = 600
    oauth_redirect_template: str = "http://localhost:8000/api/v1/auth/{provider}/callback"

    jwt_secret_key: str = "change-me"
    jwt_algorithm: str = "HS256"
    jwt_issuer: str = "eco2-auth"
    jwt_audience: str = "eco2-clients"
    access_token_exp_minutes: int = 15
    refresh_token_exp_minutes: int = 60 * 24 * 14

    # Frontend URL
    frontend_url: str = "https://frontend-beta-gray-c44lrfj3n1.vercel.app"

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

    model_config = SettingsConfigDict(env_prefix="AUTH_", env_file=".env", extra="ignore")

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
