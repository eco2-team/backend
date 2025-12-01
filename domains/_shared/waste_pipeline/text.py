import yaml
from utils import (
    load_yaml,
    load_prompt,
    get_openai_client,
    save_json_result,
    ITEM_CLASS_PATH,
    TEXT_CLASSIFICATION_PROMPT_PATH,
)
from pydantic import BaseModel
from typing import Optional

# ==========================================
# YAML 데이터 로드 및 변환
# ==========================================
item_class_yaml = load_yaml(ITEM_CLASS_PATH)
item_class_text = yaml.dump(item_class_yaml, allow_unicode=True)


class Classification(BaseModel):
    major_category: str
    middle_category: str
    minor_category: Optional[str]


class Meta(BaseModel):
    user_input: str


class TextClassificationResult(BaseModel):
    classification: Classification
    meta: Meta


# ==========================================
# GPT-5.1을 사용한 텍스트 기반 분류
# ==========================================
def classify_text(user_input_text: str, save_result: bool = False) -> dict:
    """
    텍스트만으로 폐기물 분류 결과를 반환

    Args:
        user_input_text: 사용자 입력 텍스트
        save_result: 결과를 JSON 파일로 저장할지 여부 (기본값: False)

    Returns:
        분류 결과 dict:
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

    user_xml = f"""
<context id="user_input">
{user_input_text}
</context>
""".strip()

    # GPT-5.1 호출 (chat.completions.parse 사용)
    response = client.chat.completions.parse(
        model="gpt-5.1",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_xml},
        ],
        response_format=TextClassificationResult,
    )

    parsed = response.choices[0].message.parsed  # Pydantic 모델로 반환됨

    # 결과 저장 (선택적)
    if save_result:
        saved_path = save_json_result(
            parsed.model_dump(), "text_classification", subfolder="text/classification"
        )
        print(f"✅ 텍스트 분류 결과가 저장되었습니다: {saved_path}")

    return parsed.model_dump()
