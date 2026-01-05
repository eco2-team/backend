"""Vision Model Port - 이미지 분석 추상화."""

from abc import ABC, abstractmethod
from typing import Any


class VisionModelPort(ABC):
    """Vision 모델 포트 - 이미지 분석.

    OpenAI Vision, Gemini Vision 등 다양한 구현체를 DI로 주입.
    """

    @abstractmethod
    def analyze_image(
        self,
        prompt: str,
        image_url: str,
        user_input: str | None = None,
    ) -> dict[str, Any]:
        """이미지 분석 후 분류 결과 반환.

        Args:
            prompt: 시스템 프롬프트 (분류체계, 상황태그 포함)
            image_url: 분석할 이미지 URL
            user_input: 사용자 입력 텍스트 (기본: "이 폐기물을 분류해주세요.")

        Returns:
            분류 결과 dict:
            {
                "classification": {
                    "major_category": "대분류",
                    "middle_category": "중분류",
                    "minor_category": "소분류"
                },
                "situation_tags": ["태그1", "태그2"],
                "meta": {
                    "user_input": "사용자 입력"
                }
            }
        """
        pass
