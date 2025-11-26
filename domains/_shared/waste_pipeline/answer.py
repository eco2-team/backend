from __future__ import annotations

import json
from typing import Any, Dict

from .utils import (
    ANSWER_GENERATION_PROMPT_PATH,
    get_openai_client,
    load_prompt,
    save_json_result,
)


# ==========================================
# 자연어 답변 생성 (GPT-5 Mini)
# ==========================================
def generate_answer(
    classification_result: dict,
    disposal_rules: dict,
    save_result: bool = True,
) -> Dict[str, Any]:
    """
    분류 결과와 배출 규정을 기반으로 자연어 안내문을 생성

    Args:
        classification_result: Vision API의 분류 결과 JSON
        disposal_rules: 매칭된 JSON 파일의 배출 규정
        save_result: 결과를 JSON 파일로 저장할지 여부 (기본값: True)

    Returns:
        자연어 안내문 JSON (dict):
        - disposal_steps: 배출 절차 단계별 설명
        - insufficiencies: 미흡한 항목 리스트
        - user_answer: 사용자 질문에 대한 답변
    """
    client = get_openai_client()

    # 시스템 프롬프트 로드
    system_prompt = load_prompt(ANSWER_GENERATION_PROMPT_PATH)

    # disposal_rules에서 필요한 정보 추출
    disposal_common = disposal_rules.get("배출방법_공통", {})
    disposal_detail = disposal_rules.get("배출방법_세부", {})
    disposal_forbidden = disposal_rules.get("배출불가_품목_안내", {})

    # user message 데이터 구성
    user_data = {
        "classification": classification_result.get("classification", {}),
        "situation_tags": classification_result.get("situation_tags", []),
        "meta": classification_result.get("meta", {}),
        "lite_rag_result": {
            "배출방법_공통": disposal_common,
            "배출방법_세부": disposal_detail,
            "배출불가_품목_안내": disposal_forbidden,
        },
    }

    # JSON 문자열로 변환
    user_message = json.dumps(user_data, ensure_ascii=False, indent=2)

    # GPT-5 Mini 호출
    response = client.chat.completions.create(
        model="gpt-5-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
    )

    # 응답을 JSON으로 파싱
    answer_text = response.choices[0].message.content if response.choices else None
    if not answer_text:
        raise RuntimeError("답변 생성 결과를 가져오지 못했습니다.")

    try:
        answer_json: Dict[str, Any] = json.loads(answer_text)
    except json.JSONDecodeError as exc:
        raise RuntimeError("답변 JSON 파싱에 실패했습니다.") from exc

    # 결과 저장 (선택적)
    if save_result:
        # 전체 결과를 하나의 JSON 파일로 저장
        full_result = {
            "classification_result": classification_result,
            "disposal_rules": disposal_rules,
            "final_answer": answer_json,
        }
        save_json_result(full_result, "answer")

    return answer_json
