"""Google Gemini Vision Adapter - VisionModelPort 구현체.

Gemini 3 API generate_content 사용 (gemini-3-flash-preview).
https://ai.google.dev/gemini-api/docs/gemini-3
"""

from __future__ import annotations

import logging
import os
from typing import Any, List, Optional

import httpx
from google import genai
from google.genai import types
from pydantic import BaseModel

from scan_worker.application.classify.ports.vision_model import VisionModelPort
from scan_worker.infrastructure.llm.gemini.config import (
    GEMINI_CONNECT_TIMEOUT,
    GEMINI_READ_TIMEOUT,
    MAX_OUTPUT_TOKENS,
    TEMPERATURE,
)

logger = logging.getLogger(__name__)


# ==========================================
# Pydantic 모델 (구조화 출력)
# ==========================================


class Classification(BaseModel):
    """분류 결과."""

    major_category: str
    middle_category: str
    minor_category: Optional[str] = None


class Meta(BaseModel):
    """메타 정보."""

    user_input: str


class VisionResult(BaseModel):
    """Vision API 응답 구조."""

    classification: Classification
    situation_tags: List[str]
    meta: Meta


class GeminiVisionAdapter(VisionModelPort):
    """Google Gemini Vision API 구현체.

    Gemini 3 API (google-genai 패키지) 사용.
    https://ai.google.dev/gemini-api/docs/gemini-3
    """

    def __init__(
        self,
        model: str = "gemini-3-flash-preview",
        api_key: str | None = None,
    ):
        """초기화.

        Args:
            model: Gemini 모델명 (기본: gemini-3-flash-preview)
            api_key: Google API 키 (None이면 GOOGLE_API_KEY 환경변수 사용)
        """
        # API 키 설정
        key = api_key or os.getenv("GOOGLE_API_KEY")
        if key:
            self._client = genai.Client(api_key=key)
        else:
            self._client = genai.Client()

        self._model = model
        self._http_client = httpx.Client(
            timeout=httpx.Timeout(
                connect=GEMINI_CONNECT_TIMEOUT,
                read=GEMINI_READ_TIMEOUT,
            )
        )
        logger.info(
            "GeminiVisionAdapter initialized (model=%s)",
            model,
        )

    def _fetch_image_bytes(self, image_url: str) -> tuple[bytes, str]:
        """URL에서 이미지 바이트 다운로드.

        Args:
            image_url: 이미지 URL

        Returns:
            (이미지 바이트, MIME 타입) 튜플
        """
        response = self._http_client.get(image_url)
        response.raise_for_status()

        # Content-Type 헤더에서 MIME 타입 추출
        content_type = response.headers.get("content-type", "image/jpeg")
        # charset 등 제거 (예: "image/jpeg; charset=utf-8" → "image/jpeg")
        mime_type = content_type.split(";")[0].strip()

        return response.content, mime_type

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
            분류 결과 dict
        """
        # 사용자 입력 결정
        input_text = user_input or "이 폐기물을 분류해주세요."

        logger.debug("Vision API call starting (model=%s)", self._model)

        # 이미지 다운로드
        image_bytes, mime_type = self._fetch_image_bytes(image_url)

        # 콘텐츠 구성 (이미지 + 프롬프트 + 사용자 입력)
        contents = [
            types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
            f"{prompt}\n\n{input_text}",
        ]

        # Gemini 3 API 호출 (구조화 출력)
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

        # JSON 파싱 및 Pydantic 검증
        try:
            parsed = VisionResult.model_validate_json(response.text)
            result = parsed.model_dump()
        except Exception as e:
            logger.warning("JSON parsing failed, using fallback: %s", e)
            # fallback
            result = {
                "classification": {
                    "major_category": "unknown",
                    "middle_category": "unknown",
                    "minor_category": None,
                },
                "situation_tags": [],
                "meta": {"user_input": input_text},
            }

        logger.debug(
            "Vision API call completed (major=%s, middle=%s)",
            result.get("classification", {}).get("major_category"),
            result.get("classification", {}).get("middle_category"),
        )

        return result
