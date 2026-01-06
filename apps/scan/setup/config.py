"""Scan Service Configuration.

외부화 원칙:
- 자주 바뀌는 정책(모델 목록, CORS, hosts) → env/ConfigMap
- 내부 서비스 주소 → env (로컬은 localhost, prod는 k8s DNS)
- API Key → SecretStr (로깅 마스킹)
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# ==========================================
# 모델 → Provider 명시적 매핑 (추론 없음)
# ==========================================

MODEL_PROVIDER_MAP: dict[str, str] = {
    # === GPT 계열 (OpenAI) ===
    "gpt-5.2": "gpt",
    "gpt-5.2-pro": "gpt",
    "gpt-5.1": "gpt",
    "gpt-5": "gpt",
    "gpt-5-pro": "gpt",
    "gpt-5-mini": "gpt",
    # === Gemini 계열 (Google) ===
    "gemini-3-pro-preview": "gemini",
    "gemini-3-flash-preview": "gemini",
    "gemini-2.5-pro": "gemini",
    "gemini-2.5-flash": "gemini",
    "gemini-2.5-flash-lite": "gemini",
    "gemini-2.0-flash": "gemini",
    "gemini-2.0-flash-lite": "gemini",
}

DEFAULT_CORS_ORIGINS = (
    "https://frontend.dev.growbin.app,"
    "https://frontend1.dev.growbin.app,"
    "https://frontend2.dev.growbin.app,"
    "http://localhost:5173"
)
DEFAULT_IMAGE_HOSTS = "images.dev.growbin.app,images.growbin.app"


class Settings(BaseSettings):
    """Scan Service 설정.

    운영 환경에서는 반드시 env로 주입할 것.
    """

    # === Service Identity ===
    service_name: str = Field("scan-api", description="Service name")
    service_version: str = Field("2.0.0", description="Service version")
    environment: str = Field("dev", description="Environment (dev, staging, prod)")

    # === Database ===
    database_url: str = Field(
        "postgresql+asyncpg://test:test@localhost:5432/test",
        description="PostgreSQL connection URL. prod에서는 env 필수.",
    )

    # === LLM API Keys (SecretStr로 로깅 마스킹) ===
    openai_api_key: SecretStr = Field(
        ...,
        validation_alias=AliasChoices("OPENAI_API_KEY", "SCAN_OPENAI_API_KEY"),
        description="OpenAI API key",
    )
    gemini_api_key: SecretStr | None = Field(
        None,
        validation_alias=AliasChoices("GEMINI_API_KEY", "SCAN_GEMINI_API_KEY"),
        description="Google Gemini API key",
    )

    # === LLM 모델 정책 ===
    llm_default_model: str = Field(
        "gpt-5.2",
        description="Default LLM model (클라이언트 미지정 시)",
    )

    # === Character Service ===
    character_api_base_url: str = Field(
        "http://localhost:8001",
        description="Character API base URL. prod에서는 env 필수.",
    )
    character_grpc_target: str = Field(
        "localhost:50051",
        description="Character gRPC target. prod에서는 env 필수.",
    )
    character_api_token: SecretStr | None = Field(
        None,
        description="Character API token",
    )
    character_match_timeout: int = Field(
        10,
        ge=1,
        le=60,
        description="Character match timeout (seconds)",
    )
    reward_feature_enabled: bool = Field(True, description="Enable reward feature")

    # === Redis ===
    redis_streams_url: str = Field(
        "redis://localhost:6379/0",
        description="Redis Streams URL (Events). prod에서는 env 필수.",
    )
    redis_cache_url: str = Field(
        "redis://localhost:6379/0",
        description="Redis Cache URL (Results). prod에서는 env 필수.",
    )
    result_cache_ttl: int = Field(3600, ge=60, description="Result cache TTL (seconds)")

    # === Celery ===
    celery_broker_url: str = Field(
        "amqp://guest:guest@localhost:5672//",
        description="Celery broker URL (RabbitMQ). prod에서는 env 필수.",
    )

    # === Auth ===
    auth_disabled: bool = Field(
        False,
        validation_alias=AliasChoices("SCAN_AUTH_DISABLED"),
        description="Disable authentication (dev only)",
    )

    # === CORS (env 외부화) ===
    cors_origins_str: str = Field(
        DEFAULT_CORS_ORIGINS,
        description="Allowed CORS origins (콤마 구분)",
    )

    @property
    def cors_origins(self) -> list[str]:
        """CORS origins 파싱."""
        return [o.strip() for o in self.cors_origins_str.split(",") if o.strip()]

    # === Image Validation (env 외부화) ===
    allowed_image_hosts_str: str = Field(
        DEFAULT_IMAGE_HOSTS,
        description="Allowed image CDN hosts (콤마 구분)",
    )

    @property
    def allowed_image_hosts(self) -> frozenset[str]:
        """Allowed hosts 파싱."""
        hosts = self.allowed_image_hosts_str.split(",")
        return frozenset(h.strip() for h in hosts if h.strip())

    # === OpenTelemetry ===
    otel_enabled: bool = Field(True, description="Enable OpenTelemetry tracing")
    otel_exporter_otlp_endpoint: str = Field(
        "http://localhost:4317",
        description="OTLP exporter endpoint. prod에서는 env 필수.",
    )

    model_config = SettingsConfigDict(
        env_prefix="SCAN_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ==========================================
    # Public Methods (명시적 매핑 기반)
    # ==========================================

    def resolve_provider(self, model: str) -> str:
        """모델 → provider 매핑 (명시적).

        Args:
            model: LLM 모델명

        Returns:
            provider (gpt, gemini)

        Raises:
            KeyError: 지원하지 않는 모델
        """
        if model not in MODEL_PROVIDER_MAP:
            raise KeyError(
                f"Unknown model: '{model}'. " f"Supported: {list(MODEL_PROVIDER_MAP.keys())}"
            )
        return MODEL_PROVIDER_MAP[model]

    def validate_model(self, model: str) -> bool:
        """모델이 지원되는지 검증."""
        return model in MODEL_PROVIDER_MAP

    def get_all_supported_models(self) -> list[str]:
        """모든 지원 모델 목록 반환."""
        return list(MODEL_PROVIDER_MAP.keys())


@lru_cache
def get_settings() -> Settings:
    """캐시된 Settings 인스턴스 반환."""
    return Settings()
