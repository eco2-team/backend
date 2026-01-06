"""LLMProvider Enum Tests."""

import pytest

from scan.domain.enums import LLMProvider


class TestLLMProvider:
    """LLMProvider enum 테스트."""

    def test_openai_value(self):
        """OpenAI provider 값 확인."""
        assert LLMProvider.OPENAI.value == "openai"

    def test_gemini_value(self):
        """Gemini provider 값 확인."""
        assert LLMProvider.GEMINI.value == "gemini"

    def test_str_enum(self):
        """str enum으로 문자열 비교 가능."""
        assert LLMProvider.OPENAI == "openai"
        assert LLMProvider.GEMINI == "gemini"

    def test_from_string(self):
        """문자열에서 enum 생성."""
        assert LLMProvider("openai") == LLMProvider.OPENAI
        assert LLMProvider("gemini") == LLMProvider.GEMINI

    def test_invalid_provider_raises(self):
        """잘못된 provider는 ValueError 발생."""
        with pytest.raises(ValueError):
            LLMProvider("invalid")

    def test_all_providers(self):
        """모든 provider 목록 확인."""
        providers = list(LLMProvider)
        assert len(providers) == 2
        assert LLMProvider.OPENAI in providers
        assert LLMProvider.GEMINI in providers
