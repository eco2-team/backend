"""Gemini Vision Client - Gemini Pro Vision 이미지 분석.

Clean Architecture:
- VisionModelPort 구현체
- Google Gemini Vision API 호출
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx
from google import genai
from google.genai import types
from pydantic import BaseModel

from chat_worker.application.ports.vision import VisionModelPort
from chat_worker.infrastructure.assets.prompt_loader import load_prompt_file

logger = logging.getLogger(__name__)

# Gemini 설정
MAX_OUTPUT_TOKENS = 1024
TEMPERATURE = 0.1


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


class GeminiVisionClient(VisionModelPort):
    """Google Gemini Vision 클라이언트."""

    def __init__(
        self,
        model: str = "gemini-3-flash-preview",
        api_key: str | None = None,
    ):
        """초기화.

        Args:
            model: 모델명 (기본: gemini-3-flash-preview)
            api_key: API 키 (None이면 환경변수에서)
        """
        self._model = model
        self._client = genai.Client(
            api_key=api_key or os.environ.get("GOOGLE_API_KEY"),
        )
        self._prompt = self._load_prompt()

    def _load_prompt(self) -> str:
        """프롬프트 로드."""
        try:
            return load_prompt_file("classification", "vision")
        except FileNotFoundError:
            logger.warning("Vision prompt not found, using default")
            return "이 이미지의 폐기물을 분류해주세요."

    async def _fetch_image_bytes(self, image_url: str) -> tuple[bytes, str]:
        """이미지 다운로드.

        Args:
            image_url: 이미지 URL

        Returns:
            (이미지 바이트, MIME 타입)
        """
        async with httpx.AsyncClient() as client:
            response = await client.get(image_url, timeout=30.0)
            response.raise_for_status()

        content_type = response.headers.get("content-type", "image/jpeg")
        mime_type = content_type.split(";")[0].strip()

        return response.content, mime_type

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

        logger.debug("Gemini Vision API call (model=%s)", self._model)

        try:
            # 이미지 다운로드
            image_bytes, mime_type = await self._fetch_image_bytes(image_url)

            # 콘텐츠 구성
            contents = [
                types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                f"{self._prompt}\n\n{input_text}",
            ]

            # Gemini API 호출
            response = self._client.models.generate_content(
                model=self._model,
                contents=contents,
                config={
                    "response_mime_type": "application/json",
                    "response_schema": VisionResult,
                    "max_output_tokens": MAX_OUTPUT_TOKENS,
                    "temperature": TEMPERATURE,
                },
            )

            # JSON 파싱
            parsed = VisionResult.model_validate_json(response.text)
            result = parsed.model_dump()

            logger.info(
                "Gemini Vision completed (major=%s)",
                result.get("classification", {}).get("major_category"),
            )
            return result

        except Exception as e:
            logger.error("Gemini Vision failed: %s", e)
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
