"""Application Settings.

기존 domains/auth/setup/config.py와 호환되는 환경변수 설정.
env_prefix="AUTH_" 사용으로 AUTH_GOOGLE_CLIENT_ID 등의 환경변수 매핑.
"""

from functools import lru_cache
from typing import Optional

from pydantic import AliasChoices, Field, HttpUrl, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """애플리케이션 설정.

    환경변수에서 자동으로 로드됩니다.
    env_prefix="AUTH_" 사용으로 기존 K8s ConfigMap/Secret과 호환됩니다.

    예시:
        AUTH_GOOGLE_CLIENT_ID → google_client_id
        AUTH_DATABASE_URL → database_url
    """

    # Service
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

    # Users gRPC service integration
    users_grpc_target: str = "users-api-grpc.users.svc.cluster.local:50051"
    grpc_timeout_seconds: float = 5.0
    grpc_max_retries: int = 3
    grpc_retry_base_delay: float = 0.1
    grpc_retry_max_delay: float = 2.0
    grpc_circuit_fail_max: int = 5
    grpc_circuit_timeout_duration: int = 30  # seconds

    @property
    def oauth_failure_redirect_url(self) -> str:
        return f"{self.frontend_url}/login?error=oauth_failed"

    # OAuth Providers - Google
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: Optional[HttpUrl] = None

    # OAuth Providers - Kakao
    kakao_client_id: str = ""
    kakao_client_secret: Optional[str] = None
    kakao_redirect_uri: Optional[HttpUrl] = None

    # OAuth Providers - Naver
    naver_client_id: str = ""
    naver_client_secret: str = ""
    naver_redirect_uri: Optional[HttpUrl] = None

    # OpenTelemetry (prefix 없이 직접 매핑)
    otel_service_name: str = Field(
        default="auth-api",
        validation_alias=AliasChoices("OTEL_SERVICE_NAME", "AUTH_OTEL_SERVICE_NAME"),
    )
    otel_exporter_endpoint: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("OTEL_EXPORTER_OTLP_ENDPOINT", "AUTH_OTEL_EXPORTER_ENDPOINT"),
    )

    model_config = SettingsConfigDict(
        env_prefix="AUTH_",  # ✅ 기존과 동일: AUTH_GOOGLE_CLIENT_ID → google_client_id
        case_sensitive=False,
        extra="ignore",
        validate_default=True,
    )

    @field_validator(
        "kakao_redirect_uri", "google_redirect_uri", "naver_redirect_uri", mode="before"
    )
    @classmethod
    def _empty_string_to_none(cls, value: Optional[str]):
        """빈 문자열을 None으로 변환."""
        if isinstance(value, str) and not value.strip():
            return None
        return value


@lru_cache
def get_settings() -> Settings:
    """캐시된 Settings 인스턴스 반환 (FastAPI 공식 패턴)."""
    return Settings()
