"""Vision Model Port - 이미지 분류 추상 인터페이스.

Clean Architecture:
- Application Layer에서 정의하는 추상 Port
- Infrastructure Layer에서 GPT/Gemini Vision으로 구현
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class VisionModelPort(ABC):
    """Vision 모델 Port.

    이미지를 분석하여 폐기물 분류 결과를 반환합니다.

    반환 형식:
    ```python
    {
        "classification": {
            "major_category": "재활용폐기물",
            "middle_category": "플라스틱류",
            "minor_category": "페트병",
        },
        "situation_tags": ["세척필요", "라벨제거필요"],
        "confidence": 0.95,
        "meta": {"user_input": "..."},
    }
    ```
    """

    @abstractmethod
    async def analyze_image(
        self,
        image_url: str,
        user_input: str | None = None,
    ) -> dict[str, Any]:
        """이미지 분석.

        Args:
            image_url: 분석할 이미지 URL
            user_input: 사용자 추가 설명 (선택)

        Returns:
            분류 결과 dict
        """
        pass
