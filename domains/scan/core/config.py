"""
Runtime Settings (FastAPI Official Pattern)

환경변수 기반 동적 설정 - 배포 환경별로 변경됨
Reference: https://fastapi.tiangolo.com/advanced/settings/
"""

from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for the Scan service."""

    app_name: str = "Scan API"

    # Database
    database_url: str = Field(
        "postgresql+asyncpg://test:test@localhost:5432/test",
        description="PostgreSQL connection URL for async operations.",
    )

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

    # === gRPC Retry & Circuit Breaker Settings ===
    grpc_timeout_seconds: float = Field(
        5.0,
        ge=0.1,
        le=60.0,
        description="Timeout in seconds for gRPC calls.",
    )
    grpc_max_retries: int = Field(
        3,
        ge=0,
        le=10,
        description="Maximum retry attempts for transient gRPC failures.",
    )
    grpc_retry_base_delay: float = Field(
        0.1,
        ge=0.01,
        le=5.0,
        description="Base delay in seconds for exponential backoff.",
    )
    grpc_retry_max_delay: float = Field(
        2.0,
        ge=0.1,
        le=30.0,
        description="Maximum delay in seconds for exponential backoff.",
    )
    grpc_circuit_fail_max: int = Field(
        5,
        ge=1,
        le=20,
        description="Number of failures before circuit breaker opens.",
    )
    grpc_circuit_timeout_duration: int = Field(
        30,
        ge=5,
        le=300,
        description="Seconds the circuit breaker stays open before half-open.",
    )

    # === CORS Settings ===
    cors_origins: list[str] = Field(
        default=[
            "https://frontend1.dev.growbin.app",
            "https://frontend2.dev.growbin.app",
            "https://frontend.dev.growbin.app",
            "http://localhost:5173",
            "https://localhost:5173",
            "http://127.0.0.1:5173",
            "https://127.0.0.1:5173",
        ],
        description="Allowed CORS origins.",
    )
    cors_allow_credentials: bool = Field(
        default=True,
        description="Allow credentials in CORS requests.",
    )

    auth_disabled: bool = Field(
        False,
        validation_alias=AliasChoices("SCAN_AUTH_DISABLED"),
        description="When true, skips token validation (use only for local dev).",
    )

    # === Image URL Validation ===
    allowed_image_hosts: frozenset[str] = Field(
        default_factory=lambda: frozenset(
            {
                "images.dev.growbin.app",
                "images.growbin.app",
            }
        ),
        description="허용된 이미지 CDN 호스트 목록",
    )
    allowed_image_channels: frozenset[str] = Field(
        default_factory=lambda: frozenset({"chat", "scan", "my"}),
        description="허용된 이미지 채널 (URL 경로의 첫 번째 세그먼트)",
    )
    allowed_image_extensions: frozenset[str] = Field(
        default_factory=lambda: frozenset({".jpg", ".jpeg", ".png", ".webp", ".gif"}),
        description="허용된 이미지 확장자",
    )
    image_filename_pattern: str = Field(
        r"^[a-f0-9]{32}$",
        description="이미지 파일명 패턴 (확장자 제외, UUID hex 32자)",
    )

    model_config = SettingsConfigDict(
        env_prefix="SCAN_",
        case_sensitive=False,
        extra="ignore",
        validate_default=True,
    )


@lru_cache
def get_settings() -> Settings:
    """Return cached Settings instance (FastAPI pattern)."""
    return Settings()
