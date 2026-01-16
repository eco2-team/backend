"""OpenAI Vision Client - GPT-4V 이미지 분석.

Clean Architecture:
- VisionModelPort 구현체
- OpenAI GPT-4V API 호출
"""

from __future__ import annotations

import logging
import os
from typing import Any

from openai import OpenAI
from pydantic import BaseModel

from chat_worker.application.ports.vision import VisionModelPort
from chat_worker.infrastructure.assets.prompt_loader import load_prompt_file

logger = logging.getLogger(__name__)


class Classification(BaseModel):
    """분류 결과."""

    major_category: str
    middle_category: str
    minor_category: str | None = None


class VisionResult(BaseModel):
    """Vision 분석 결과."""

    classification: Classification
    situation_tags: list[str] = []
    confidence: float = 0.0


class OpenAIVisionClient(VisionModelPort):
    """OpenAI GPT-4V Vision 클라이언트."""

    def __init__(
        self,
        model: str = "gpt-5.2",
        api_key: str | None = None,
    ):
        """초기화.

        Args:
            model: 모델명 (기본: gpt-5.2, 멀티모달 지원)
            api_key: API 키 (None이면 환경변수에서)
        """
        self._model = model
        self._client = OpenAI(api_key=api_key or os.environ.get("OPENAI_API_KEY"))
        self._prompt = self._load_prompt()

    def _load_prompt(self) -> str:
        """프롬프트 로드."""
        try:
            return load_prompt_file("classification", "vision")
        except FileNotFoundError:
            logger.warning("Vision prompt not found, using default")
            return "이 이미지의 폐기물을 분류해주세요."

    async def analyze_image(
        self,
        image_url: str,
        user_input: str | None = None,
    ) -> dict[str, Any]:
        """이미지 분석.

        Args:
            image_url: 분석할 이미지 URL
            user_input: 사용자 추가 설명

        Returns:
            분류 결과 dict
        """
        input_text = user_input or "이 폐기물을 분류해주세요."

        logger.debug("OpenAI Vision API call (model=%s)", self._model)

        try:
            response = self._client.beta.chat.completions.parse(
                model=self._model,
                messages=[
                    {"role": "system", "content": self._prompt},
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": input_text},
                            {
                                "type": "image_url",
                                "image_url": {"url": image_url, "detail": "high"},
                            },
                        ],
                    },
                ],
                response_format=VisionResult,
            )

            parsed = response.choices[0].message.parsed
            result = parsed.model_dump() if parsed else self._fallback_result(input_text)

            logger.info(
                "OpenAI Vision completed (major=%s)",
                result.get("classification", {}).get("major_category"),
            )
            return result

        except Exception as e:
            logger.error("OpenAI Vision failed: %s", e)
            return self._fallback_result(input_text)

    def _fallback_result(self, user_input: str) -> dict[str, Any]:
        """Fallback 결과."""
        return {
            "classification": {
                "major_category": "unknown",
                "middle_category": "unknown",
                "minor_category": None,
            },
            "situation_tags": [],
            "confidence": 0.0,
            "meta": {"user_input": user_input, "error": "fallback"},
        }
