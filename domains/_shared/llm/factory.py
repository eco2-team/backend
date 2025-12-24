"""LLM Provider 팩토리."""

from __future__ import annotations

import logging
from functools import lru_cache

from .base import LLMProvider
from .config import LLMConfig, ProviderType, get_config

logger = logging.getLogger(__name__)

_provider_instance: LLMProvider | None = None


def _create_provider(config: LLMConfig) -> LLMProvider:
    """설정에 따라 Provider 인스턴스 생성."""
    if config.provider == ProviderType.GEMINI:
        from .gemini_provider import GeminiProvider

        logger.info(
            "Creating Gemini provider",
            extra={
                "vision_model": config.vision_model,
                "chat_model": config.chat_model,
            },
        )
        return GeminiProvider(config)
    else:
        from .openai_provider import OpenAIProvider

        logger.info(
            "Creating OpenAI provider",
            extra={
                "vision_model": config.vision_model,
                "chat_model": config.chat_model,
            },
        )
        return OpenAIProvider(config)


@lru_cache(maxsize=1)
def get_llm_provider() -> LLMProvider:
    """싱글톤 LLM Provider 반환.

    환경변수 기반으로 OpenAI 또는 Gemini Provider 선택.

    Returns:
        LLMProvider 인스턴스

    Example:
        provider = get_llm_provider()
        result = await provider.vision_analyze(request, ResponseModel)
    """
    config = get_config()
    return _create_provider(config)


def get_async_llm_provider() -> LLMProvider:
    """비동기 컨텍스트용 LLM Provider 반환.

    현재는 동기/비동기 Provider가 동일하지만,
    향후 비동기 전용 최적화가 필요할 경우 분리 가능.
    """
    return get_llm_provider()


def reset_provider() -> None:
    """Provider 캐시 초기화 (테스트용)."""
    get_llm_provider.cache_clear()
    get_config.cache_clear()
