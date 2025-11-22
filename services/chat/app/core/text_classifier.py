import json
import yaml
from utils import (
    load_yaml,
    load_prompt,
    get_openai_client,
    save_json_result,
    ITEM_CLASS_PATH,
    TEXT_CLASSIFICATION_PROMPT_PATH
)

# ==========================================
# YAML 데이터 로드 및 변환
# ==========================================
item_class_yaml = load_yaml(ITEM_CLASS_PATH)
item_class_text = yaml.dump(item_class_yaml, allow_unicode=True)

# ==========================================
# GPT-5-mini를 사용한 텍스트 기반 분류
# ==========================================
def classify_text(user_input_text: str, save_result: bool = False) -> str:
    """
    텍스트만으로 폐기물 분류 결과를 반환

    Args:
        user_input_text: 사용자 입력 텍스트
        save_result: 결과를 JSON 파일로 저장할지 여부 (기본값: False)

    Returns:
        분류 결과 JSON 문자열:
        {
            "classification": {
                "major_category": "대분류",
                "middle_category": "중분류",
                "minor_category": "소분류"
            },
            "meta": {
                "user_input": "사용자 입력"
            }
        }
    """
    client = get_openai_client()

    # 프롬프트 로드 및 변수 치환
    raw_prompt = load_prompt(TEXT_CLASSIFICATION_PROMPT_PATH)
    system_prompt = raw_prompt.replace("{{ITEM_CLASS_YAML}}", item_class_text)

    # GPT-5-mini 호출
    response = client.chat.completions.create(
        model="gpt-5-mini",
        messages=[
            {
                "role": "system",
                "content": system_prompt
            },
            {
                "role": "user",
                "content": user_input_text
            }
        ]
    )

    result_text = response.choices[0].message.content

    # 결과 저장 (선택적)
    if save_result:
        try:
            result_json = json.loads(result_text)
            saved_path = save_json_result(result_json, "text_classification", subfolder="text/classification")
            print(f"✅ 텍스트 분류 결과가 저장되었습니다: {saved_path}")
        except json.JSONDecodeError:
            print("⚠️  텍스트 분류 결과 저장 실패: JSON 파싱 오류")

    return result_text
