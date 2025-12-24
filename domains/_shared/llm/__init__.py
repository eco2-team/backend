"""LLM Provider 추상화 레이어.

OpenAI, Gemini 등 다양한 LLM Provider를 통합 인터페이스로 제공.
환경변수 기반으로 Provider 선택 가능.

Usage:
    from domains._shared.llm import get_llm_provider

    provider = get_llm_provider()
    result = await provider.vision_analyze(image_url, prompt, ResponseModel)
    result = await provider.chat_completion(messages, ResponseModel)

Environment Variables:
    LLM_PROVIDER: openai | gemini (default: openai)
    LLM_VISION_MODEL: 모델명 (default: gpt-5.1)
    LLM_CHAT_MODEL: 모델명 (default: gpt-5.1)
"""

from .base import LLMProvider, VisionRequest, ChatRequest
from .config import LLMConfig, get_config
from .factory import get_llm_provider, get_async_llm_provider

__all__ = [
    "LLMProvider",
    "VisionRequest",
    "ChatRequest",
    "LLMConfig",
    "get_config",
    "get_llm_provider",
    "get_async_llm_provider",
]
