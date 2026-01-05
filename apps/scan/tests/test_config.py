"""Config Tests - LLM 모델 설정 테스트."""

import os
from unittest.mock import patch



# 테스트용 환경변수 (OPENAI_API_KEY 필수)
TEST_ENV = {
    "OPENAI_API_KEY": "test-key",
}


class TestSettingsGetModel:
    """Settings.get_model() 테스트."""

    def test_get_model_openai_default(self):
        """OpenAI 기본 모델 반환."""
        with patch.dict(os.environ, TEST_ENV, clear=False):
            from apps.scan.setup.config import Settings
            settings = Settings()
            assert settings.get_model("openai") == "gpt-5.2"

    def test_get_model_gemini_default(self):
        """Gemini 기본 모델 반환."""
        with patch.dict(os.environ, TEST_ENV, clear=False):
            from apps.scan.setup.config import Settings
            settings = Settings()
            assert settings.get_model("gemini") == "gemini-3.0-flash"

    def test_get_model_unknown_fallback_to_openai(self):
        """알 수 없는 provider는 OpenAI로 fallback."""
        with patch.dict(os.environ, TEST_ENV, clear=False):
            from apps.scan.setup.config import Settings
            settings = Settings()
            assert settings.get_model("unknown") == "gpt-5.2"

    def test_get_model_custom_openai(self):
        """환경변수로 OpenAI 모델 커스텀."""
        env = {**TEST_ENV, "SCAN_LLM_OPENAI_MODEL": "gpt-6.0"}
        with patch.dict(os.environ, env, clear=False):
            from apps.scan.setup.config import Settings
            settings = Settings()
            assert settings.get_model("openai") == "gpt-6.0"

    def test_get_model_custom_gemini(self):
        """환경변수로 Gemini 모델 커스텀."""
        env = {**TEST_ENV, "SCAN_LLM_GEMINI_MODEL": "gemini-4.0-ultra"}
        with patch.dict(os.environ, env, clear=False):
            from apps.scan.setup.config import Settings
            settings = Settings()
            assert settings.get_model("gemini") == "gemini-4.0-ultra"

    def test_settings_from_env(self):
        """환경변수에서 설정 로드."""
        env_vars = {
            "OPENAI_API_KEY": "env-test-key",
            "SCAN_LLM_OPENAI_MODEL": "gpt-env-model",
            "SCAN_LLM_GEMINI_MODEL": "gemini-env-model",
        }

        with patch.dict(os.environ, env_vars, clear=False):
            from apps.scan.setup.config import Settings
            settings = Settings()
            assert settings.llm_openai_model == "gpt-env-model"
