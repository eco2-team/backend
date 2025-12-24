"""LLM Provider 설정."""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from functools import lru_cache


class ProviderType(str, Enum):
    """지원하는 LLM Provider."""

    OPENAI = "openai"
    GEMINI = "gemini"


@dataclass(frozen=True)
class LLMConfig:
    """LLM Provider 설정.

    환경변수:
        LLM_PROVIDER: openai | gemini
        LLM_VISION_MODEL: Vision 모델명
        LLM_CHAT_MODEL: Chat 모델명
        OPENAI_API_KEY: OpenAI API 키
        GOOGLE_API_KEY: Google Gemini API 키
    """

    provider: ProviderType
    vision_model: str
    chat_model: str
    api_key: str

    @classmethod
    def from_env(cls) -> LLMConfig:
        """환경변수에서 설정 로드."""
        provider_str = os.getenv("LLM_PROVIDER", "openai").lower()
        provider = ProviderType(provider_str)

        if provider == ProviderType.GEMINI:
            api_key = os.getenv("GOOGLE_API_KEY", "")
            # https://ai.google.dev/gemini-api/docs?hl=ko
            vision_model = os.getenv("LLM_VISION_MODEL", "gemini-3-flash-preview")
            chat_model = os.getenv("LLM_CHAT_MODEL", "gemini-3-flash-preview")
        else:
            api_key = os.getenv("OPENAI_API_KEY", "")
            vision_model = os.getenv("LLM_VISION_MODEL", "gpt-5.1")
            chat_model = os.getenv("LLM_CHAT_MODEL", "gpt-5.1")

        if not api_key:
            key_name = "GOOGLE_API_KEY" if provider == ProviderType.GEMINI else "OPENAI_API_KEY"
            raise RuntimeError(f"{key_name} 환경 변수가 설정되지 않았습니다.")

        return cls(
            provider=provider,
            vision_model=vision_model,
            chat_model=chat_model,
            api_key=api_key,
        )


@lru_cache(maxsize=1)
def get_config() -> LLMConfig:
    """싱글톤 설정 반환."""
    return LLMConfig.from_env()
