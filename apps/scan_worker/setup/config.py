"""Scan Worker Configuration.

외부화 원칙:
- 자주 바뀌는 정책(모델 목록) → env/ConfigMap
- 내부 서비스 주소 → env (로컬은 localhost, prod는 k8s DNS)
- API Key → SecretStr (로깅 마스킹)
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
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
    # https://ai.google.dev/gemini-api/docs/gemini-3
    "gemini-3-pro-preview": "gemini",
    "gemini-3-flash-preview": "gemini",
    "gemini-2.5-pro": "gemini",
    "gemini-2.5-flash": "gemini",
    "gemini-2.5-flash-lite": "gemini",
    "gemini-2.0-flash": "gemini",
    "gemini-2.0-flash-lite": "gemini",
}


class Settings(BaseSettings):
    """Worker 설정.

    운영 환경에서는 반드시 env로 주입할 것.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # === Celery ===
    celery_broker_url: str = Field(
        "amqp://guest:guest@localhost:5672//",
        description="Celery broker URL (RabbitMQ). prod에서는 env 필수.",
    )
    celery_result_backend: str | None = Field(
        None,
        description="Celery result backend. None이면 결과 저장 안 함.",
    )

    # === Redis ===
    redis_streams_url: str = Field(
        "redis://localhost:6379/0",
        description="Redis Streams URL (이벤트 발행). prod에서는 env 필수.",
    )
    redis_cache_url: str = Field(
        "redis://localhost:6379/0",
        description="Redis Cache URL. prod에서는 env 필수.",
    )
    sse_shard_count: int = Field(4, ge=1, le=64, description="SSE shard count")
    result_cache_ttl: int = Field(3600, ge=60, description="결과 캐시 TTL (초)")
    checkpoint_ttl: int = Field(
        3600,
        ge=60,
        description="체크포인트 TTL (초). 파이프라인 완료 전 실패 복구 윈도우.",
    )

    # === LLM API Keys (SecretStr로 로깅 마스킹) ===
    openai_api_key: SecretStr = Field(
        ...,
        description="OpenAI API Key",
    )
    gemini_api_key: SecretStr | None = Field(
        None,
        description="Gemini API Key",
    )

    # === LLM 모델 정책 ===
    llm_default_model: str = Field(
        "gpt-5.2",
        description="기본 LLM 모델명 (클라이언트 미지정 시)",
    )

    # === Character Service ===
    character_match_timeout: int = Field(
        10,
        ge=1,
        le=60,
        description="character.match task 대기 타임아웃 (초)",
    )

    # === Reward ===
    reward_enabled: bool = Field(True, description="Enable reward feature")

    # === Resources ===
    @property
    def assets_path(self) -> str:
        """정적 에셋 경로 (prompts, data).

        프롬프트 템플릿, 분류 체계, 폐기물 규정 JSON 등.
        """
        return str(Path(__file__).parent.parent / "infrastructure" / "assets")

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
        """Vision + Structured JSON 지원 모델인지 검증.

        Args:
            model: LLM 모델명

        Returns:
            지원 여부
        """
        return model in MODEL_PROVIDER_MAP

    def get_supported_models(self, provider: str | None = None) -> list[str]:
        """지원 모델 목록 반환.

        Args:
            provider: 특정 provider만 필터 (None이면 전체)

        Returns:
            지원 모델 목록
        """
        if provider:
            return [m for m, p in MODEL_PROVIDER_MAP.items() if p == provider]
        return list(MODEL_PROVIDER_MAP.keys())

    def get_api_key(self, provider: str) -> str | None:
        """Provider별 API Key 반환 (SecretStr unwrap).

        Args:
            provider: LLM provider (gpt, gemini 등)

        Returns:
            API Key 문자열 또는 None
        """
        if provider == "gemini":
            if self.gemini_api_key:
                return self.gemini_api_key.get_secret_value()
            return None
        # gpt, o1 등 OpenAI 계열
        return self.openai_api_key.get_secret_value()


@lru_cache
def get_settings() -> Settings:
    """설정 싱글톤."""
    return Settings()
