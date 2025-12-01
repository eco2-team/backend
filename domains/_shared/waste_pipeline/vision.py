import logging
from datetime import datetime, timezone
from time import perf_counter
from typing import List, Optional

import yaml
from pydantic import BaseModel

from .utils import (
    ITEM_CLASS_PATH,
    SITUATION_TAG_PATH,
    VISION_PROMPT_PATH,
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
def analyze_images(user_input_text: str, image_urls: list[str], save_result: bool = False) -> dict:
    """
    이미지와 텍스트를 분석하여 폐기물 분류 결과를 반환

    Args:
        user_input_text: 사용자 입력 텍스트
        image_urls: 분석할 이미지 URL 리스트
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
    started_at = datetime.now(timezone.utc)
    timer = perf_counter()
    success = False
    client = get_openai_client()
    logger.info(
        "Vision analyze_images started at %s (images=%d)",
        started_at.isoformat(),
        len(image_urls),
    )

    try:
        # 프롬프트 로드 및 변수 치환
        raw_prompt = load_prompt(VISION_PROMPT_PATH)
        system_prompt = raw_prompt.replace("{{ITEM_CLASS_YAML}}", item_class_text).replace(
            "{{SITUATION_TAG_YAML}}", situation_tags_text
        )

        content_items = []
        system_items = []

        system_items.append({"type": "input_text", "text": system_prompt})

        # 사용자 메시지 구성
        content_items.append({"type": "input_text", "text": user_input_text})

        # 이미지 추가
        for url in image_urls:
            content_items.append({"type": "input_image", "image_url": url})

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
        result_payload = parsed.model_dump()

        if save_result:
            saved_path = save_json_result(
                result_payload, "vision_classification", subfolder="vision/classification"
            )
            print(f"✅ 저장됨: {saved_path}")

        success = True
        return result_payload
    finally:
        finished_at = datetime.now(timezone.utc)
        elapsed_ms = (perf_counter() - timer) * 1000
        logger.info(
            "Vision analyze_images finished at %s (started_at=%s, %.1f ms, success=%s)",
            finished_at.isoformat(),
            started_at.isoformat(),
            elapsed_ms,
            success,
        )
