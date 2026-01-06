"""GPT Vision Adapter - VisionModelPort 구현체.

OpenAI responses.parse API 사용 (gpt-5.1/5.2).
"""

from __future__ import annotations

import logging
from typing import Any, List, Optional

import httpx
from openai import OpenAI
from pydantic import BaseModel

from scan_worker.application.classify.ports.vision_model import VisionModelPort
from scan_worker.infrastructure.llm.gpt.config import (
    MAX_RETRIES,
    OPENAI_LIMITS,
    OPENAI_TIMEOUT,
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


class GPTVisionAdapter(VisionModelPort):
    """GPT Vision API 구현체.

    responses.parse API 사용으로 Pydantic 구조화 출력.
    """

    def __init__(
        self,
        model: str = "gpt-5.1",
        api_key: str | None = None,
    ):
        """초기화.

        Args:
            model: GPT 모델명 (기본: gpt-5.1)
            api_key: OpenAI API 키 (None이면 환경변수 사용)
        """
        http_client = httpx.Client(
            timeout=OPENAI_TIMEOUT,
            limits=OPENAI_LIMITS,
        )
        self._client = OpenAI(
            api_key=api_key,
            http_client=http_client,
            max_retries=MAX_RETRIES,
        )
        self._model = model
        logger.info(
            "GPTVisionAdapter initialized (model=%s)",
            model,
        )

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

        # 시스템 메시지 구성
        system_items = [{"type": "input_text", "text": prompt}]

        # 사용자 메시지 구성 (이미지 + 텍스트)
        content_items = [
            {"type": "input_text", "text": input_text},
            # detail: low로 토큰 89% 절감 (85 토큰 고정)
            {"type": "input_image", "image_url": image_url, "detail": "low"},
        ]

        logger.debug("Vision API call starting (model=%s)", self._model)

        # Vision API 호출 (responses.parse)
        response = self._client.responses.parse(
            model=self._model,
            input=[
                {"role": "user", "content": content_items},
                {"role": "system", "content": system_items},
            ],
            text_format=VisionResult,
        )

        parsed = response.output_parsed
        result = parsed.model_dump()

        logger.debug(
            "Vision API call completed (major=%s, middle=%s)",
            result.get("classification", {}).get("major_category"),
            result.get("classification", {}).get("middle_category"),
        )

        return result
