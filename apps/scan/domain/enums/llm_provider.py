"""LLM Provider Enum.

지원하는 LLM Provider를 정의합니다.
Provider 목록은 안정적이며, 새 제공자 추가 시에만 변경됩니다.
모델명은 setup/config.py에서 환경 변수로 관리합니다.
"""

from enum import Enum


class LLMProvider(str, Enum):
    """지원하는 LLM Provider.

    - OPENAI: OpenAI API (GPT 시리즈)
    - GEMINI: Google Gemini API
    """

    OPENAI = "openai"
    GEMINI = "gemini"
