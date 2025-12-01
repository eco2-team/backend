import json
from utils import load_prompt, get_openai_client, save_json_result, ANSWER_GENERATION_PROMPT_PATH
from pydantic import BaseModel, Field
from typing import List, Optional


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
    client = get_openai_client()

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

    # 결과 저장 (선택적)
    if save_result:
        # 전체 결과를 하나의 JSON 파일로 저장
        full_result = {
            "classification_result": classification_result,
            "disposal_rules": disposal_rules,
            "final_answer": parsed.model_dump(),
        }
        # 파이프라인 타입에 따라 다른 폴더에 저장
        subfolder = f"{pipeline_type}/answer"
        saved_path = save_json_result(full_result, "final_answer", subfolder=subfolder)
        print(f"✅ 최종 답변이 저장되었습니다: {saved_path}")

    return parsed.model_dump()
