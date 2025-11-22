import json
from utils import (
    load_prompt,
    get_openai_client,
    save_json_result,
    ANSWER_GENERATION_PROMPT_PATH
)

# ==========================================
# 자연어 답변 생성 (GPT-5 Mini)
# ==========================================
def generate_answer(classification_result: dict, disposal_rules: dict, save_result: bool = True, pipeline_type: str = "vision") -> dict:
    """
    분류 결과와 배출 규정을 기반으로 자연어 안내문을 생성

    Args:
        classification_result: Vision API 또는 텍스트 분류 결과 JSON
        disposal_rules: 매칭된 JSON 파일의 배출 규정
        save_result: 결과를 JSON 파일로 저장할지 여부 (기본값: True)
        pipeline_type: 파이프라인 타입 ("vision" 또는 "text", 기본값: "vision")

    Returns:
        자연어 안내문 JSON (dict):
        - disposal_steps: 배출 절차 단계별 설명
        - insufficiencies: 미흡한 항목 리스트
        - user_answer: 사용자 질문에 대한 답변
    """
    client = get_openai_client()

    # 시스템 프롬프트 로드
    system_prompt = load_prompt(ANSWER_GENERATION_PROMPT_PATH)

    # user message 데이터 구성
    user_data = {
        "classification": classification_result.get("classification", {}),
        "situation_tags": classification_result.get("situation_tags", []),
        "meta": classification_result.get("meta", {}),
        "lite_rag_result": disposal_rules  # 전체 disposal_rules를 통째로 전달
    }

    # JSON 문자열로 변환
    user_message = json.dumps(user_data, ensure_ascii=False, indent=2)

    # GPT-5 Mini 호출
    response = client.chat.completions.create(
        # model="gpt-5-mini",
        model="gpt-5.1",
        messages=[
            {
                "role": "system",
                "content": system_prompt
            },
            {
                "role": "user",
                "content": user_message
            }
        ]
    )

    # 응답을 JSON으로 파싱
    answer_text = response.choices[0].message.content
    answer_json = json.loads(answer_text)

    # 결과 저장 (선택적)
    if save_result:
        # 전체 결과를 하나의 JSON 파일로 저장
        full_result = {
            "classification_result": classification_result,
            "disposal_rules": disposal_rules,
            "final_answer": answer_json
        }
        # 파이프라인 타입에 따라 다른 폴더에 저장
        subfolder = f"{pipeline_type}/answer"
        saved_path = save_json_result(full_result, "final_answer", subfolder=subfolder)
        print(f"✅ 최종 답변이 저장되었습니다: {saved_path}")

    return answer_json
