import logging
import yaml
from typing import List, Optional
from pydantic import BaseModel

from .utils import (
    ITEM_CLASS_PATH,
    SITUATION_TAG_PATH,
    VISION_PROMPT_PATH,
    get_async_openai_client,
    get_openai_client,
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
    minor_category: Optional[str]


class Meta(BaseModel):
    user_input: str


class VisionResult(BaseModel):
    classification: Classification
    situation_tags: List[str]
    meta: Meta


# ==========================================
# GPT-5.1 Vision 호출 (responses API)
# ==========================================
def analyze_images(user_input_text: str, image_url: str, save_result: bool = False) -> dict:
    """
    이미지와 텍스트를 분석하여 폐기물 분류 결과를 반환

    Args:
        user_input_text: 사용자 입력 텍스트
        image_url: 분석할 이미지 URL(단일)
        save_result: 결과를 JSON 파일로 저장할지 여부 (기본값: False)

    Returns:
        분류 결과 dict:
        {
            "classification": {
                "major_category": "대분류",
                "middle_category": "중분류",
                "minor_category": "소분류"
            },
            "situation_tags": ["태그1", "태그2"],
            "meta": {
                "user_input": "사용자 입력"
            }
        }
    """
    client = get_openai_client()

    # 프롬프트 로드 및 변수 치환
    raw_prompt = load_prompt(VISION_PROMPT_PATH)
    logger.info("Vision prompt raw length: %d chars", len(raw_prompt))
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
    logger.debug("Vision system prompt content:\n%s", system_prompt)

    content_items = []
    system_items = []

    system_items.append({"type": "input_text", "text": system_prompt})

    # 사용자 메시지 구성
    content_items.append({"type": "input_text", "text": user_input_text})

    # 이미지 추가 (단일 URL) - detail: low로 토큰 89% 절감
    # low: 85 토큰 고정 (512x512 저해상도), high: 이미지 크기에 따라 765-2380 토큰
    # 폐기물 대분류/중분류 판단에는 low로 충분
    content_items.append({"type": "input_image", "image_url": image_url, "detail": "low"})
    logger.debug("Vision system items: %s", system_items)
    logger.debug("Vision content items: %s", content_items)

    # Vision API 호출
    response = client.responses.parse(
        model="gpt-5.1",
        input=[
            {"role": "user", "content": content_items},
            {"role": "system", "content": system_items},
        ],
        text_format=VisionResult,
    )

    parsed = response.output_parsed  # Pydantic 모델로 반환됨

    if save_result:
        saved_path = save_json_result(
            parsed.model_dump(), "vision_classification", subfolder="vision/classification"
        )
        print(f"✅ 저장됨: {saved_path}")

    return parsed.model_dump()


# ==========================================
# GPT-5.1 Vision 비동기 호출 (/completion SSE 전용)
# ==========================================
async def analyze_images_async(user_input_text: str, image_url: str) -> dict:
    """
    이미지와 텍스트를 비동기로 분석하여 폐기물 분류 결과를 반환.

    /completion SSE 엔드포인트 전용.
    AsyncOpenAI 클라이언트를 사용하여 I/O 블로킹 없이 처리.

    Args:
        user_input_text: 사용자 입력 텍스트
        image_url: 분석할 이미지 URL(단일)

    Returns:
        분류 결과 dict
    """
    client = get_async_openai_client()

    # 프롬프트 로드 및 변수 치환
    raw_prompt = load_prompt(VISION_PROMPT_PATH)
    system_prompt = raw_prompt.replace("{{ITEM_CLASS_YAML}}", item_class_text).replace(
        "{{SITUATION_TAG_YAML}}", situation_tags_text
    )

    system_items = [{"type": "input_text", "text": system_prompt}]
    content_items = [
        {"type": "input_text", "text": user_input_text},
        # detail: low로 토큰 89% 절감 (85 토큰 고정)
        {"type": "input_image", "image_url": image_url, "detail": "low"},
    ]

    logger.info("Vision async API call starting")

    # Vision API 비동기 호출
    response = await client.responses.parse(
        model="gpt-5.1",
        input=[
            {"role": "user", "content": content_items},
            {"role": "system", "content": system_items},
        ],
        text_format=VisionResult,
    )

    parsed = response.output_parsed
    logger.info("Vision async API call completed")

    return parsed.model_dump()
