"""LLM Model Port - 자연어 답변 생성 추상화."""

from abc import ABC, abstractmethod
from typing import Any


class LLMPort(ABC):
    """LLM 모델 포트 - 자연어 답변 생성.

    OpenAI GPT, Gemini 등 다양한 구현체를 DI로 주입.
    """

    @abstractmethod
    def generate_answer(
        self,
        classification: dict[str, Any],
        disposal_rules: dict[str, Any],
        user_input: str,
    ) -> dict[str, Any]:
        """분류 결과와 배출 규정을 기반으로 자연어 답변 생성.

        Args:
            classification: Vision 분류 결과
            disposal_rules: 매칭된 배출 규정 JSON
            user_input: 사용자 질문

        Returns:
            답변 결과 dict:
            {
                "disposal_steps": {
                    "단계1": "...",
                    "단계2": "...",
                    ...
                },
                "insufficiencies": ["미흡항목1", ...],
                "user_answer": "사용자 질문에 대한 답변"
            }
        """
        pass
