"""Config Tests - LLM 모델 설정 테스트."""

import os
from unittest.mock import patch

import pytest


# 테스트용 환경변수 (OPENAI_API_KEY 필수)
TEST_ENV = {
    "OPENAI_API_KEY": "test-key",
}


class TestSettingsResolveProvider:
    """Settings.resolve_provider() 테스트."""

    def test_resolve_provider_gpt(self):
        """GPT 모델 → gpt provider."""
        with patch.dict(os.environ, TEST_ENV, clear=False):
            from apps.scan.setup.config import Settings

            settings = Settings()
            assert settings.resolve_provider("gpt-5.2") == "gpt"
            assert settings.resolve_provider("gpt-5.1") == "gpt"
            assert settings.resolve_provider("gpt-5-mini") == "gpt"

    def test_resolve_provider_gemini(self):
        """Gemini 모델 → gemini provider."""
        with patch.dict(os.environ, TEST_ENV, clear=False):
            from apps.scan.setup.config import Settings

            settings = Settings()
            assert settings.resolve_provider("gemini-2.5-pro") == "gemini"
            assert settings.resolve_provider("gemini-2.5-flash") == "gemini"

    def test_resolve_provider_unknown_raises(self):
        """알 수 없는 모델은 KeyError."""
        with patch.dict(os.environ, TEST_ENV, clear=False):
            from apps.scan.setup.config import Settings

            settings = Settings()
            with pytest.raises(KeyError):
                settings.resolve_provider("unknown-model")


class TestSettingsValidateModel:
    """Settings.validate_model() 테스트."""

    def test_validate_model_supported(self):
        """지원 모델 검증."""
        with patch.dict(os.environ, TEST_ENV, clear=False):
            from apps.scan.setup.config import Settings

            settings = Settings()
            assert settings.validate_model("gpt-5.2") is True
            assert settings.validate_model("gemini-2.5-pro") is True

    def test_validate_model_unsupported(self):
        """미지원 모델 검증."""
        with patch.dict(os.environ, TEST_ENV, clear=False):
            from apps.scan.setup.config import Settings

            settings = Settings()
            assert settings.validate_model("unknown-model") is False


class TestSettingsDefaults:
    """Settings 기본값 테스트."""

    def test_default_model(self):
        """기본 LLM 모델."""
        with patch.dict(os.environ, TEST_ENV, clear=False):
            from apps.scan.setup.config import Settings

            settings = Settings()
            assert settings.llm_default_model == "gpt-5.2"

    def test_custom_default_model(self):
        """환경변수로 기본 모델 변경."""
        env = {**TEST_ENV, "SCAN_LLM_DEFAULT_MODEL": "gpt-5-mini"}
        with patch.dict(os.environ, env, clear=False):
            from apps.scan.setup.config import Settings

            settings = Settings()
            assert settings.llm_default_model == "gpt-5-mini"

    def test_get_all_supported_models(self):
        """지원 모델 목록 확인."""
        with patch.dict(os.environ, TEST_ENV, clear=False):
            from apps.scan.setup.config import Settings

            settings = Settings()
            models = settings.get_all_supported_models()
            assert "gpt-5.2" in models
            assert "gemini-2.5-pro" in models
            assert len(models) > 0
