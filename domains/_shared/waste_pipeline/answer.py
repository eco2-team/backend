"""자연어 답변 생성.

LLM Provider 추상화를 통해 OpenAI, Gemini 등 다양한 Provider 지원.
환경변수 LLM_PROVIDER로 Provider 선택 가능.
"""

import json
import logging
from datetime import datetime, timezone
from time import perf_counter
from typing import List, Optional

from pydantic import BaseModel, Field

from domains._shared.llm import ChatRequest, get_llm_provider

from .utils import (
    ANSWER_GENERATION_PROMPT_PATH,
    load_prompt,
    save_json_result,
)

logger = logging.getLogger(__name__)


class DisposalSteps(BaseModel):
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
    disposal_steps: DisposalSteps
    insufficiencies: List[str] = Field(default_factory=list)
    user_answer: str


def _build_user_message(classification_result: dict, disposal_rules: dict) -> str:
    """사용자 메시지 구성."""
    classification_json = json.dumps(
        classification_result.get("classification", {}), ensure_ascii=False, indent=2
    )
    tags_json = json.dumps(
        classification_result.get("situation_tags", []), ensure_ascii=False, indent=2
    )
    rag_json = json.dumps(disposal_rules, ensure_ascii=False, indent=2)
    user_input_text = classification_result.get("meta", {}).get("user_input", "")

    return f"""
    <context id="classification">
    {classification_json}
    </context>

    <context id="situation_tags">
    {tags_json}
    </context>

    <context id="user_input">
    {user_input_text}
    </context>

    <context id="lite_rag">
    {rag_json}
    </context>
    """


# ==========================================
# 자연어 답변 생성 (동기)
# ==========================================
def generate_answer(
    classification_result: dict,
    disposal_rules: dict,
    save_result: bool = True,
    pipeline_type: str = "vision",
) -> dict:
    """
    분류 결과와 배출 규정을 기반으로 자연어 안내문을 생성.

    Args:
        classification_result: Vision API 또는 텍스트 분류 결과 dict
        disposal_rules: 매칭된 JSON 파일의 배출 규정
        save_result: 결과를 JSON 파일로 저장할지 여부 (기본값: True)
        pipeline_type: 파이프라인 타입 ("vision" 또는 "text", 기본값: "vision")

    Returns:
        자연어 안내문 dict
    """
    started_at = datetime.now(timezone.utc)
    timer = perf_counter()
    success = False
    provider = get_llm_provider()

    logger.info(
        "Answer generation started at %s (provider=%s, pipeline_type=%s)",
        started_at.isoformat(),
        provider.name,
        pipeline_type,
    )

    try:
        system_prompt = load_prompt(ANSWER_GENERATION_PROMPT_PATH)
        logger.info("Answer prompt loaded (%d chars)", len(system_prompt))

        user_message = _build_user_message(classification_result, disposal_rules)
        logger.debug("Answer user message preview: %s", user_message[:500])

        request = ChatRequest(
            messages=[{"role": "user", "content": user_message}],
            system_prompt=system_prompt,
        )

        result_payload = provider.chat_completion_sync(request, AnswerResult)

        if save_result:
            full_result = {
                "classification_result": classification_result,
                "disposal_rules": disposal_rules,
                "final_answer": result_payload,
            }
            subfolder = f"{pipeline_type}/answer"
            saved_path = save_json_result(full_result, "final_answer", subfolder=subfolder)
            print(f"✅ 최종 답변이 저장되었습니다: {saved_path}")

        success = True
        return result_payload

    finally:
        finished_at = datetime.now(timezone.utc)
        elapsed_ms = (perf_counter() - timer) * 1000
        logger.info(
            "Answer generation finished at %s (started_at=%s, %.1f ms, success=%s)",
            finished_at.isoformat(),
            started_at.isoformat(),
            elapsed_ms,
            success,
        )


# ==========================================
# 자연어 답변 비동기 생성 (/completion SSE 전용)
# ==========================================
async def generate_answer_async(
    classification_result: dict,
    disposal_rules: dict,
) -> dict:
    """
    분류 결과와 배출 규정을 기반으로 자연어 안내문을 비동기로 생성.

    /completion SSE 엔드포인트 전용.
    I/O 블로킹 없이 처리.

    Args:
        classification_result: Vision API 또는 텍스트 분류 결과 dict
        disposal_rules: 매칭된 JSON 파일의 배출 규정

    Returns:
        자연어 안내문 dict
    """
    started_at = datetime.now(timezone.utc)
    timer = perf_counter()
    provider = get_llm_provider()

    logger.info(
        "Answer async generation started at %s (provider=%s)",
        started_at.isoformat(),
        provider.name,
    )

    system_prompt = load_prompt(ANSWER_GENERATION_PROMPT_PATH)
    user_message = _build_user_message(classification_result, disposal_rules)

    request = ChatRequest(
        messages=[{"role": "user", "content": user_message}],
        system_prompt=system_prompt,
    )

    result_payload = await provider.chat_completion(request, AnswerResult)

    elapsed_ms = (perf_counter() - timer) * 1000
    logger.info("Answer async generation completed (%.1f ms)", elapsed_ms)

    return result_payload
