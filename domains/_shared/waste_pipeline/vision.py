"""Vision API를 통한 폐기물 분류.

LLM Provider 추상화를 통해 OpenAI, Gemini 등 다양한 Provider 지원.
환경변수 LLM_PROVIDER로 Provider 선택 가능.
"""

import logging
from typing import List, Optional

import yaml
from pydantic import BaseModel

from domains._shared.llm import VisionRequest, get_llm_provider

from .utils import (
    ITEM_CLASS_PATH,
    SITUATION_TAG_PATH,
    VISION_PROMPT_PATH,
    load_prompt,
    load_yaml,
    save_json_result,
)

logger = logging.getLogger(__name__)

# ==========================================
# YAML 데이터 로드 및 변환
# ==========================================
item_class_yaml = load_yaml(ITEM_CLASS_PATH)
situation_tags_yaml = load_yaml(SITUATION_TAG_PATH)

item_class_text = yaml.dump(item_class_yaml, allow_unicode=True)
situation_tags_text = yaml.dump(situation_tags_yaml, allow_unicode=True)


class Classification(BaseModel):
    major_category: str
    middle_category: str
    minor_category: Optional[str] = None


class Meta(BaseModel):
    user_input: str


class VisionResult(BaseModel):
    classification: Classification
    situation_tags: List[str]
    meta: Meta


def _build_system_prompt() -> str:
    """시스템 프롬프트 생성."""
    raw_prompt = load_prompt(VISION_PROMPT_PATH)
    system_prompt = raw_prompt.replace("{{ITEM_CLASS_YAML}}", item_class_text).replace(
        "{{SITUATION_TAG_YAML}}", situation_tags_text
    )

    missing_tokens = [
        token
        for token in ("{{ITEM_CLASS_YAML}}", "{{SITUATION_TAG_YAML}}")
        if token in system_prompt
    ]
    if missing_tokens:
        logger.warning("Vision prompt still has unresolved tokens: %s", missing_tokens)
    else:
        logger.info(
            "Vision prompt prepared (item_class=%d chars, situation_tags=%d chars)",
            len(item_class_text),
            len(situation_tags_text),
        )

    return system_prompt


# ==========================================
# Vision 분석 (동기)
# ==========================================
def analyze_images(user_input_text: str, image_url: str, save_result: bool = False) -> dict:
    """
    이미지와 텍스트를 분석하여 폐기물 분류 결과를 반환.

    Args:
        user_input_text: 사용자 입력 텍스트
        image_url: 분석할 이미지 URL(단일)
        save_result: 결과를 JSON 파일로 저장할지 여부 (기본값: False)

    Returns:
        분류 결과 dict
    """
    provider = get_llm_provider()
    system_prompt = _build_system_prompt()

    logger.info("Vision analysis starting (provider=%s)", provider.name)

    request = VisionRequest(
        image_url=image_url,
        prompt=user_input_text,
        system_prompt=system_prompt,
    )

    result = provider.vision_analyze_sync(request, VisionResult)

    if save_result:
        saved_path = save_json_result(
            result, "vision_classification", subfolder="vision/classification"
        )
        print(f"✅ 저장됨: {saved_path}")

    logger.info("Vision analysis completed (provider=%s)", provider.name)
    return result


# ==========================================
# Vision 분석 (비동기) - /completion SSE 전용
# ==========================================
async def analyze_images_async(user_input_text: str, image_url: str) -> dict:
    """
    이미지와 텍스트를 비동기로 분석하여 폐기물 분류 결과를 반환.

    /completion SSE 엔드포인트 전용.
    I/O 블로킹 없이 처리.

    Args:
        user_input_text: 사용자 입력 텍스트
        image_url: 분석할 이미지 URL(단일)

    Returns:
        분류 결과 dict
    """
    provider = get_llm_provider()
    system_prompt = _build_system_prompt()

    logger.info("Vision async API call starting (provider=%s)", provider.name)

    request = VisionRequest(
        image_url=image_url,
        prompt=user_input_text,
        system_prompt=system_prompt,
    )

    result = await provider.vision_analyze(request, VisionResult)

    logger.info("Vision async API call completed (provider=%s)", provider.name)
    return result
