"""Image Generator Adapters.

멀티 Provider 이미지 생성 구현체.

지원 Provider:
- OpenAI: Responses API (gpt-image-1.5)
- Gemini: Native Image Generation (gemini-3-pro-image-preview)

팩토리 함수:
- create_image_generator(): Provider에 맞는 생성기 자동 선택
"""

from __future__ import annotations

from chat_worker.application.ports.image_generator import ImageGeneratorPort
from chat_worker.domain.models.provider import Provider, get_model_config
from chat_worker.infrastructure.llm.image_generator.gemini_native import (
    GeminiNativeImageGenerator,
)
from chat_worker.infrastructure.llm.image_generator.openai_responses import (
    OpenAIResponsesImageGenerator,
)

__all__ = [
    "GeminiNativeImageGenerator",
    "OpenAIResponsesImageGenerator",
    "create_image_generator",
]


def create_image_generator(
    model_id: str | None = None,
    provider: Provider | str | None = None,
) -> ImageGeneratorPort:
    """Provider에 맞는 ImageGenerator 생성.

    메인 모델 ID 또는 Provider를 기반으로 적절한 이미지 생성기를 선택합니다.

    Args:
        model_id: 메인 모델 ID (예: "openai/gpt-5.2", "gemini/gemini-3.0-preview")
        provider: Provider 직접 지정 (model_id보다 우선)

    Returns:
        ImageGeneratorPort 구현체

    Examples:
        >>> gen = create_image_generator(model_id="openai/gpt-5.2")
        >>> # OpenAIResponsesImageGenerator (gpt-image-1.5)

        >>> gen = create_image_generator(model_id="gemini/gemini-3.0-preview")
        >>> # GeminiNativeImageGenerator (gemini-3-pro-image-preview)

        >>> gen = create_image_generator(provider=Provider.GEMINI)
        >>> # GeminiNativeImageGenerator
    """
    # 모델 설정 조회
    config = get_model_config(model_id) if model_id else None

    # Provider 결정
    if provider:
        if isinstance(provider, str):
            provider = Provider(provider)
    elif config:
        provider = config.provider
    else:
        provider = Provider.OPENAI

    # Provider별 생성기 반환
    if provider == Provider.GEMINI:
        gemini_model = (
            config.image_model if config and config.image_model else "gemini-3-pro-image-preview"
        )
        return GeminiNativeImageGenerator(model=gemini_model)

    # OpenAI (기본)
    openai_model = config.model_name if config else "gpt-5.2"
    return OpenAIResponsesImageGenerator(model=openai_model)
