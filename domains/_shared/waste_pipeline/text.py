"""텍스트 기반 폐기물 분류.

LLM Provider 추상화를 통해 OpenAI, Gemini 등 다양한 Provider 지원.
환경변수 LLM_PROVIDER로 Provider 선택 가능.
"""

import logging
from typing import Optional

import yaml
from pydantic import BaseModel

from domains._shared.llm import ChatRequest, get_llm_provider

from .utils import (
    ITEM_CLASS_PATH,
    TEXT_CLASSIFICATION_PROMPT_PATH,
    load_prompt,
    load_yaml,
    save_json_result,
)

logger = logging.getLogger(__name__)

# ==========================================
# YAML 데이터 로드 및 변환
# ==========================================
item_class_yaml = load_yaml(ITEM_CLASS_PATH)
item_class_text = yaml.dump(item_class_yaml, allow_unicode=True)


class Classification(BaseModel):
    major_category: str
    middle_category: str
    minor_category: Optional[str] = None


class Meta(BaseModel):
    user_input: str


class TextClassificationResult(BaseModel):
    classification: Classification
    meta: Meta


# ==========================================
# 텍스트 기반 분류 (동기)
# ==========================================
def classify_text(user_input_text: str, save_result: bool = False) -> dict:
    """
    텍스트만으로 폐기물 분류 결과를 반환.

    Args:
        user_input_text: 사용자 입력 텍스트
        save_result: 결과를 JSON 파일로 저장할지 여부 (기본값: False)

    Returns:
        분류 결과 dict
    """
    provider = get_llm_provider()

    # 프롬프트 로드 및 변수 치환
    raw_prompt = load_prompt(TEXT_CLASSIFICATION_PROMPT_PATH)
    system_prompt = raw_prompt.replace("{{ITEM_CLASS_YAML}}", item_class_text)

    user_xml = f"""
<context id="user_input">
{user_input_text}
</context>
""".strip()

    logger.info("Text classification starting (provider=%s)", provider.name)

    request = ChatRequest(
        messages=[{"role": "user", "content": user_xml}],
        system_prompt=system_prompt,
    )

    result = provider.chat_completion_sync(request, TextClassificationResult)

    if save_result:
        saved_path = save_json_result(
            result, "text_classification", subfolder="text/classification"
        )
        print(f"✅ 텍스트 분류 결과가 저장되었습니다: {saved_path}")

    logger.info("Text classification completed (provider=%s)", provider.name)
    return result


def process_text_classification(user_input_text: str, save_result: bool = False) -> dict:
    """Legacy wrapper for backwards compatibility."""
    return classify_text(user_input_text, save_result=save_result)
