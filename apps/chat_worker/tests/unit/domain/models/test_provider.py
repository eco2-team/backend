"""Provider and Model Registry Tests."""

import pytest

from chat_worker.domain.models.provider import (
    DEFAULT_IMAGE_MODELS,
    MODEL_REGISTRY,
    ModelCapabilities,
    Provider,
    get_image_capable_models,
    get_image_model,
    get_model_config,
    get_models_by_provider,
)


class TestProvider:
    """Provider enum 테스트."""

    def test_openai_value(self):
        """OpenAI provider 값 확인."""
        assert Provider.OPENAI.value == "openai"

    def test_google_value(self):
        """Google provider 값 확인."""
        assert Provider.GOOGLE.value == "google"

    def test_str_enum(self):
        """str enum으로 문자열 비교 가능."""
        assert Provider.OPENAI == "openai"
        assert Provider.GOOGLE == "google"

    def test_from_string(self):
        """문자열에서 enum 생성."""
        assert Provider("openai") == Provider.OPENAI
        assert Provider("google") == Provider.GOOGLE

    def test_invalid_provider_raises(self):
        """잘못된 provider는 ValueError 발생."""
        with pytest.raises(ValueError):
            Provider("invalid")


class TestModelCapabilities:
    """ModelCapabilities 테스트."""

    def test_default_values(self):
        """기본값 확인."""
        caps = ModelCapabilities()
        assert caps.supports_tools is True
        assert caps.supports_vision is False
        assert caps.supports_image_generation is False
        assert caps.max_reference_images == 0
        assert caps.supports_audio is False

    def test_custom_values(self):
        """커스텀 값 설정."""
        caps = ModelCapabilities(
            supports_tools=False,
            supports_vision=True,
            supports_image_generation=True,
            max_reference_images=5,
            supports_audio=True,
        )
        assert caps.supports_tools is False
        assert caps.supports_vision is True
        assert caps.supports_image_generation is True
        assert caps.max_reference_images == 5
        assert caps.supports_audio is True

    def test_frozen(self):
        """frozen dataclass - 변경 불가."""
        caps = ModelCapabilities()
        with pytest.raises(AttributeError):
            caps.supports_tools = False  # type: ignore


class TestModelConfig:
    """ModelConfig 테스트."""

    def test_openai_model_config(self):
        """OpenAI 모델 설정 확인."""
        config = MODEL_REGISTRY["openai/gpt-5.2"]
        assert config.id == "openai/gpt-5.2"
        assert config.provider == Provider.OPENAI
        assert config.model_name == "gpt-5.2"
        assert config.display_name == "GPT-5.2"
        assert config.image_model == "gpt-image-1.5"
        assert config.context_window == 400000
        assert config.max_output_tokens == 128000

    def test_google_model_config(self):
        """Google 모델 설정 확인."""
        config = MODEL_REGISTRY["google/gemini-3-pro-preview"]
        assert config.id == "google/gemini-3-pro-preview"
        assert config.provider == Provider.GOOGLE
        assert config.model_name == "gemini-3-pro-preview"
        assert config.display_name == "Gemini 3 Pro Preview"
        assert config.image_model == "gemini-3-pro-image-preview"
        assert config.context_window == 1000000
        assert config.max_output_tokens == 64000

    def test_openai_capabilities(self):
        """OpenAI 모델 기능 확인."""
        config = MODEL_REGISTRY["openai/gpt-5.2"]
        caps = config.capabilities
        assert caps.supports_tools is True
        assert caps.supports_vision is True
        assert caps.supports_image_generation is True
        assert caps.max_reference_images == 1
        assert caps.supports_audio is True

    def test_google_capabilities(self):
        """Google 모델 기능 확인."""
        config = MODEL_REGISTRY["google/gemini-3-pro-preview"]
        caps = config.capabilities
        assert caps.supports_tools is True
        assert caps.supports_vision is True
        assert caps.supports_image_generation is True
        assert caps.max_reference_images == 14
        assert caps.supports_audio is True


class TestGetModelConfig:
    """get_model_config() 테스트."""

    def test_get_by_full_id(self):
        """전체 ID로 조회."""
        config = get_model_config("openai/gpt-5.2")
        assert config is not None
        assert config.id == "openai/gpt-5.2"

    def test_get_by_model_name(self):
        """모델명만으로 조회."""
        config = get_model_config("gpt-5.2")
        assert config is not None
        assert config.model_name == "gpt-5.2"

    def test_get_google_by_model_name(self):
        """Google 모델명으로 조회."""
        config = get_model_config("gemini-3-pro-preview")
        assert config is not None
        assert config.provider == Provider.GOOGLE

    def test_unknown_model_returns_none(self):
        """미등록 모델은 None 반환."""
        config = get_model_config("unknown-model")
        assert config is None

    def test_partial_match_returns_none(self):
        """부분 매칭은 None 반환."""
        config = get_model_config("gpt")
        assert config is None


class TestGetImageModel:
    """get_image_model() 테스트."""

    def test_openai_image_model(self):
        """OpenAI 기본 이미지 모델."""
        model = get_image_model(Provider.OPENAI)
        assert model == "gpt-image-1.5"

    def test_google_image_model(self):
        """Google 기본 이미지 모델."""
        model = get_image_model(Provider.GOOGLE)
        assert model == "gemini-3-pro-image-preview"

    def test_default_image_models_dict(self):
        """DEFAULT_IMAGE_MODELS 상수 확인."""
        assert Provider.OPENAI in DEFAULT_IMAGE_MODELS
        assert Provider.GOOGLE in DEFAULT_IMAGE_MODELS


class TestGetModelsByProvider:
    """get_models_by_provider() 테스트."""

    def test_openai_models(self):
        """OpenAI 모델 목록."""
        models = get_models_by_provider(Provider.OPENAI)
        assert len(models) >= 1
        assert all(m.provider == Provider.OPENAI for m in models)

    def test_google_models(self):
        """Google 모델 목록."""
        models = get_models_by_provider(Provider.GOOGLE)
        assert len(models) >= 1
        assert all(m.provider == Provider.GOOGLE for m in models)


class TestGetImageCapableModels:
    """get_image_capable_models() 테스트."""

    def test_returns_image_capable_only(self):
        """이미지 생성 가능 모델만 반환."""
        models = get_image_capable_models()
        assert len(models) >= 2
        assert all(m.capabilities.supports_image_generation for m in models)

    def test_includes_both_providers(self):
        """양쪽 Provider 모두 포함."""
        models = get_image_capable_models()
        providers = {m.provider for m in models}
        assert Provider.OPENAI in providers
        assert Provider.GOOGLE in providers
