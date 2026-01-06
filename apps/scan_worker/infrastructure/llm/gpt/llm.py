"""GPT LLM Adapter - LLMPort 구현체.

OpenAI chat.completions.parse API 사용 (gpt-5.1/5.2).
"""

from __future__ import annotations

import json
import logging
from typing import Any, List, Optional

import httpx
from openai import OpenAI
from pydantic import BaseModel, Field

from scan_worker.application.classify.ports.llm_model import LLMPort
from scan_worker.infrastructure.llm.gpt.config import (
    MAX_RETRIES,
    OPENAI_LIMITS,
    OPENAI_TIMEOUT,
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


class GPTLLMAdapter(LLMPort):
    """GPT LLM API 구현체.

    chat.completions.parse API 사용으로 Pydantic 구조화 출력.
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
            "GPTLLMAdapter initialized (model=%s)",
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

        # 사용자 메시지 구성
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

        user_message = f"""
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

        # LLM API 호출 (chat.completions.parse)
        response = self._client.chat.completions.parse(
            model=self._model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            response_format=AnswerResult,
        )

        parsed = response.choices[0].message.parsed
        result = parsed.model_dump()

        logger.debug("LLM API call completed")

        return result
