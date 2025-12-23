import json
import logging
from datetime import datetime, timezone
from time import perf_counter
from typing import List, Optional

from pydantic import BaseModel, Field

from .utils import (
    ANSWER_GENERATION_PROMPT_PATH,
    get_async_openai_client,
    get_openai_client,
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


# ==========================================
# 자연어 답변 생성 (GPT-5.1)
# ==========================================
def generate_answer(
    classification_result: dict,
    disposal_rules: dict,
    save_result: bool = True,
    pipeline_type: str = "vision",
) -> dict:
    """
    분류 결과와 배출 규정을 기반으로 자연어 안내문을 생성

    Args:
        classification_result: Vision API 또는 텍스트 분류 결과 dict
        disposal_rules: 매칭된 JSON 파일의 배출 규정
        save_result: 결과를 JSON 파일로 저장할지 여부 (기본값: True)
        pipeline_type: 파이프라인 타입 ("vision" 또는 "text", 기본값: "vision")

    Returns:
        자연어 안내문 dict:
        - disposal_steps: 배출 절차 단계별 설명
        - insufficiencies: 미흡한 항목 리스트
        - user_answer: 사용자 질문에 대한 답변
    """
    started_at = datetime.now(timezone.utc)
    timer = perf_counter()
    success = False
    client = get_openai_client()
    logger.info(
        "Answer generation started at %s (pipeline_type=%s)",
        started_at.isoformat(),
        pipeline_type,
    )

    try:
        # 시스템 프롬프트 로드
        system_prompt = load_prompt(ANSWER_GENERATION_PROMPT_PATH)
        logger.info("Answer prompt loaded (%d chars)", len(system_prompt))
        logger.debug("Answer system prompt content:\n%s", system_prompt)

        classification_json = json.dumps(
            classification_result.get("classification", {}), ensure_ascii=False, indent=2
        )

        tags_json = json.dumps(
            classification_result.get("situation_tags", []), ensure_ascii=False, indent=2
        )

        rag_json = json.dumps(disposal_rules, ensure_ascii=False, indent=2)

        user_input_text = classification_result.get("meta", {}).get("user_input", "")

        user_message = f"""
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
        logger.debug("Answer user message preview: %s", user_message[:500])
        logger.debug("Answer user message full:\n%s", user_message)

        # GPT-5.1 호출 (chat.completions.parse 사용)
        response = client.chat.completions.parse(
            model="gpt-5.1",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            response_format=AnswerResult,
        )

        parsed = response.choices[0].message.parsed  # Pydantic 모델로 반환됨
        result_payload = parsed.model_dump()

        # 결과 저장 (선택적)
        if save_result:
            # 전체 결과를 하나의 JSON 파일로 저장
            full_result = {
                "classification_result": classification_result,
                "disposal_rules": disposal_rules,
                "final_answer": result_payload,
            }
            # 파이프라인 타입에 따라 다른 폴더에 저장
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
    AsyncOpenAI 클라이언트를 사용하여 I/O 블로킹 없이 처리.

    Args:
        classification_result: Vision API 또는 텍스트 분류 결과 dict
        disposal_rules: 매칭된 JSON 파일의 배출 규정

    Returns:
        자연어 안내문 dict
    """
    started_at = datetime.now(timezone.utc)
    timer = perf_counter()
    client = get_async_openai_client()

    logger.info("Answer async generation started at %s", started_at.isoformat())

    # 시스템 프롬프트 로드
    system_prompt = load_prompt(ANSWER_GENERATION_PROMPT_PATH)

    classification_json = json.dumps(
        classification_result.get("classification", {}), ensure_ascii=False, indent=2
    )
    tags_json = json.dumps(
        classification_result.get("situation_tags", []), ensure_ascii=False, indent=2
    )
    rag_json = json.dumps(disposal_rules, ensure_ascii=False, indent=2)
    user_input_text = classification_result.get("meta", {}).get("user_input", "")

    user_message = f"""
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

    # GPT-5.1 비동기 호출
    response = await client.chat.completions.parse(
        model="gpt-5.1",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        response_format=AnswerResult,
    )

    parsed = response.choices[0].message.parsed
    result_payload = parsed.model_dump()

    elapsed_ms = (perf_counter() - timer) * 1000
    logger.info("Answer async generation completed (%.1f ms)", elapsed_ms)

    return result_payload
