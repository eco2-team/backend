"""Google Gemini LLM Adapter - LLMPort 구현체.

Gemini 3 API generate_content 사용 (gemini-3-flash-preview).
https://ai.google.dev/gemini-api/docs/gemini-3
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, List, Optional

from google import genai
from pydantic import BaseModel, Field

from scan_worker.application.classify.ports.llm_model import LLMPort
from scan_worker.infrastructure.llm.gemini.config import (
    MAX_OUTPUT_TOKENS,
    TEMPERATURE,
)

logger = logging.getLogger(__name__)


# ==========================================
# Pydantic 모델 (구조화 출력)
# ==========================================


class DisposalSteps(BaseModel):
    """배출 절차 단계."""

    단계1: Optional[str] = None
    단계2: Optional[str] = None
    단계3: Optional[str] = None
    단계4: Optional[str] = None
    단계5: Optional[str] = None
    단계6: Optional[str] = None
    단계7: Optional[str] = None
    단계8: Optional[str] = None
    단계9: Optional[str] = None
    단계10: Optional[str] = None


class AnswerResult(BaseModel):
    """답변 생성 결과."""

    disposal_steps: DisposalSteps
    insufficiencies: List[str] = Field(default_factory=list)
    user_answer: str


class GeminiLLMAdapter(LLMPort):
    """Google Gemini LLM API 구현체.

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
        logger.info(
            "GeminiLLMAdapter initialized (model=%s)",
            model,
        )

    def generate_answer(
        self,
        classification: dict[str, Any],
        disposal_rules: dict[str, Any],
        user_input: str,
        system_prompt: str | None = None,
    ) -> dict[str, Any]:
        """분류 결과와 배출 규정을 기반으로 자연어 답변 생성.

        Args:
            classification: Vision 분류 결과
            disposal_rules: 매칭된 배출 규정 JSON
            user_input: 사용자 질문
            system_prompt: 시스템 프롬프트 (None이면 기본값)

        Returns:
            답변 결과 dict
        """
        # 기본 시스템 프롬프트
        if system_prompt is None:
            system_prompt = "당신은 폐기물 분리배출 전문가입니다."

        # 컨텍스트 메시지 구성
        classification_json = json.dumps(
            classification.get("classification", {}),
            ensure_ascii=False,
            indent=2,
        )
        tags_json = json.dumps(
            classification.get("situation_tags", []),
            ensure_ascii=False,
            indent=2,
        )
        rag_json = json.dumps(disposal_rules, ensure_ascii=False, indent=2)

        # Gemini는 시스템 프롬프트를 별도로 지원하지 않으므로 앞에 추가
        full_prompt = f"""{system_prompt}

<context id="classification">
{classification_json}
</context>

<context id="situation_tags">
{tags_json}
</context>

<context id="user_input">
{user_input}
</context>

<context id="lite_rag">
{rag_json}
</context>
"""

        logger.debug("LLM API call starting (model=%s)", self._model)

        # Gemini 3 API 호출 (구조화 출력)
        response = self._client.models.generate_content(
            model=self._model,
            contents=full_prompt,
            config={
                "response_mime_type": "application/json",
                "response_schema": AnswerResult,
                "max_output_tokens": MAX_OUTPUT_TOKENS,
                "temperature": TEMPERATURE,
            },
        )

        # JSON 파싱 및 Pydantic 검증
        try:
            parsed = AnswerResult.model_validate_json(response.text)
            result = parsed.model_dump()
        except Exception as e:
            logger.warning("JSON parsing failed, using raw response: %s", e)
            # fallback: 원본 텍스트 반환
            result = {
                "disposal_steps": {},
                "insufficiencies": [],
                "user_answer": response.text,
            }

        logger.debug("LLM API call completed")

        return result
