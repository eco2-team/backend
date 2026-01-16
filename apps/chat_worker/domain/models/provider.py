"""Provider and Model Registry.

OpenCode 스타일의 멀티 모델 지원을 위한 Provider/Model 추상화.

설계 원칙:
- Provider: LLM 제공자 (OpenAI, Google 등)
- ModelConfig: 모델별 설정 및 기능 정의
- 자동 이미지 모델 매핑: 메인 모델 선택 시 적합한 이미지 모델 자동 연결

사용 예시:
```python
# 메인 모델에서 이미지 모델 자동 선택
config = get_model_config("openai/gpt-5.2")
image_model = config.image_model  # "gpt-image-1.5"

# Provider별 이미지 모델 직접 조회
image_model = get_image_model(Provider.GEMINI)  # "gemini-3-pro-image-preview"
```
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Provider(str, Enum):
    """LLM Provider."""

    OPENAI = "openai"
    GEMINI = "gemini"
    ANTHROPIC = "anthropic"  # 이미지 생성 미지원, 향후 확장용


@dataclass(frozen=True)
class ModelCapabilities:
    """모델 기능 정의.

    Attributes:
        supports_tools: Tool Calling 지원 여부
        supports_vision: 이미지 입력 지원 여부
        supports_image_generation: 이미지 생성 지원 여부
        max_reference_images: 참조 이미지 최대 개수 (0이면 미지원)
        supports_audio: 오디오 입출력 지원 여부
    """

    supports_tools: bool = True
    supports_vision: bool = False
    supports_image_generation: bool = False
    max_reference_images: int = 0
    supports_audio: bool = False


@dataclass(frozen=True)
class ModelConfig:
    """모델 설정.

    Attributes:
        id: 전체 모델 ID (provider/model 형식)
        provider: Provider enum
        model_name: Provider 내 모델명
        display_name: UI 표시용 이름
        image_model: 연결된 이미지 생성 모델 (None이면 미지원)
        capabilities: 모델 기능 정의
        context_window: 컨텍스트 윈도우 크기
        max_output_tokens: 최대 출력 토큰
    """

    id: str
    provider: Provider
    model_name: str
    display_name: str
    image_model: str | None
    capabilities: ModelCapabilities
    context_window: int = 128000
    max_output_tokens: int = 8192


# ============================================================================
# Model Registry
# ============================================================================
# OpenCode 스타일: 모든 지원 모델을 레지스트리에 등록
# 새 모델 추가 시 여기에 등록

MODEL_REGISTRY: dict[str, ModelConfig] = {
    # -------------------------------------------------------------------------
    # OpenAI Models
    # -------------------------------------------------------------------------
    "openai/gpt-5.2": ModelConfig(
        id="openai/gpt-5.2",
        provider=Provider.OPENAI,
        model_name="gpt-5.2",
        display_name="GPT-5.2",
        image_model="gpt-image-1.5",
        capabilities=ModelCapabilities(
            supports_tools=True,
            supports_vision=True,
            supports_image_generation=True,
            max_reference_images=0,  # OpenAI는 reference 미지원
            supports_audio=True,
        ),
        context_window=400000,
        max_output_tokens=128000,
    ),
    "openai/gpt-4.1": ModelConfig(
        id="openai/gpt-4.1",
        provider=Provider.OPENAI,
        model_name="gpt-4.1",
        display_name="GPT-4.1",
        image_model="gpt-image-1.5",
        capabilities=ModelCapabilities(
            supports_tools=True,
            supports_vision=True,
            supports_image_generation=True,
            max_reference_images=0,
        ),
        context_window=1047576,
        max_output_tokens=32768,
    ),
    "openai/gpt-4.1-mini": ModelConfig(
        id="openai/gpt-4.1-mini",
        provider=Provider.OPENAI,
        model_name="gpt-4.1-mini",
        display_name="GPT-4.1 Mini",
        image_model="gpt-image-1.5",
        capabilities=ModelCapabilities(
            supports_tools=True,
            supports_vision=True,
            supports_image_generation=True,
            max_reference_images=0,
        ),
        context_window=1047576,
        max_output_tokens=32768,
    ),
    # -------------------------------------------------------------------------
    # Google Gemini Models
    # -------------------------------------------------------------------------
    "gemini/gemini-3.0-preview": ModelConfig(
        id="gemini/gemini-3.0-preview",
        provider=Provider.GEMINI,
        model_name="gemini-3.0-preview",
        display_name="Gemini 3.0 Preview",
        image_model="gemini-3-pro-image-preview",
        capabilities=ModelCapabilities(
            supports_tools=True,
            supports_vision=True,
            supports_image_generation=True,
            max_reference_images=14,  # 캐릭터 5개 포함
            supports_audio=True,
        ),
        context_window=2000000,
        max_output_tokens=65536,
    ),
    "gemini/gemini-3-flash-preview": ModelConfig(
        id="gemini/gemini-3-flash-preview",
        provider=Provider.GEMINI,
        model_name="gemini-3-flash-preview",
        display_name="Gemini 3 Flash",
        image_model="gemini-2.5-flash-image",
        capabilities=ModelCapabilities(
            supports_tools=True,
            supports_vision=True,
            supports_image_generation=True,
            max_reference_images=3,  # Flash는 최대 3개
            supports_audio=True,
        ),
        context_window=1000000,
        max_output_tokens=65536,
    ),
    "gemini/gemini-2.5-pro": ModelConfig(
        id="gemini/gemini-2.5-pro",
        provider=Provider.GEMINI,
        model_name="gemini-2.5-pro",
        display_name="Gemini 2.5 Pro",
        image_model="gemini-2.5-flash-image",
        capabilities=ModelCapabilities(
            supports_tools=True,
            supports_vision=True,
            supports_image_generation=True,
            max_reference_images=3,
        ),
        context_window=1000000,
        max_output_tokens=65536,
    ),
    # -------------------------------------------------------------------------
    # Anthropic Models (이미지 생성 미지원)
    # -------------------------------------------------------------------------
    "anthropic/claude-opus-4": ModelConfig(
        id="anthropic/claude-opus-4",
        provider=Provider.ANTHROPIC,
        model_name="claude-opus-4-20250514",
        display_name="Claude Opus 4",
        image_model=None,  # 이미지 생성 미지원
        capabilities=ModelCapabilities(
            supports_tools=True,
            supports_vision=True,
            supports_image_generation=False,
            max_reference_images=0,
        ),
        context_window=200000,
        max_output_tokens=32000,
    ),
    "anthropic/claude-sonnet-4": ModelConfig(
        id="anthropic/claude-sonnet-4",
        provider=Provider.ANTHROPIC,
        model_name="claude-sonnet-4-20250514",
        display_name="Claude Sonnet 4",
        image_model=None,
        capabilities=ModelCapabilities(
            supports_tools=True,
            supports_vision=True,
            supports_image_generation=False,
            max_reference_images=0,
        ),
        context_window=200000,
        max_output_tokens=64000,
    ),
}

# Provider별 기본 이미지 모델
DEFAULT_IMAGE_MODELS: dict[Provider, str] = {
    Provider.OPENAI: "gpt-image-1.5",
    Provider.GEMINI: "gemini-3-pro-image-preview",
}


def get_model_config(model_id: str) -> ModelConfig | None:
    """모델 ID로 설정 조회.

    Args:
        model_id: 전체 모델 ID (provider/model) 또는 모델명만

    Returns:
        ModelConfig 또는 None (미등록 모델)

    Examples:
        >>> config = get_model_config("openai/gpt-5.2")
        >>> config.image_model
        'gpt-image-1.5'

        >>> config = get_model_config("gpt-5.2")  # provider 없이도 검색
        >>> config.provider
        Provider.OPENAI
    """
    # 전체 ID로 검색
    if model_id in MODEL_REGISTRY:
        return MODEL_REGISTRY[model_id]

    # 모델명만으로 검색 (첫 번째 매칭)
    for config in MODEL_REGISTRY.values():
        if config.model_name == model_id:
            return config

    return None


def get_image_model(provider: Provider) -> str | None:
    """Provider별 기본 이미지 모델 조회.

    Args:
        provider: LLM Provider

    Returns:
        이미지 모델명 또는 None
    """
    return DEFAULT_IMAGE_MODELS.get(provider)


def get_models_by_provider(provider: Provider) -> list[ModelConfig]:
    """Provider별 모든 모델 조회.

    Args:
        provider: LLM Provider

    Returns:
        해당 Provider의 모든 ModelConfig 목록
    """
    return [config for config in MODEL_REGISTRY.values() if config.provider == provider]


def get_image_capable_models() -> list[ModelConfig]:
    """이미지 생성 가능한 모델 목록.

    Returns:
        이미지 생성을 지원하는 모든 ModelConfig 목록
    """
    return [
        config
        for config in MODEL_REGISTRY.values()
        if config.capabilities.supports_image_generation
    ]
