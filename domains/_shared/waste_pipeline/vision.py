from __future__ import annotations

import yaml

from .utils import (
    ITEM_CLASS_PATH,
    SITUATION_TAG_PATH,
    VISION_PROMPT_PATH,
    get_openai_client,
    load_prompt,
    load_yaml,
)

# ==========================================
# YAML 데이터 로드 및 변환
# ==========================================
item_class_yaml = load_yaml(ITEM_CLASS_PATH)
situation_tags_yaml = load_yaml(SITUATION_TAG_PATH)

item_class_text = yaml.dump(item_class_yaml, allow_unicode=True)
situation_tags_text = yaml.dump(situation_tags_yaml, allow_unicode=True)


# ==========================================
# GPT-5.1 Vision 호출 (responses API)
# ==========================================
def analyze_images(user_input_text: str, image_urls: list[str]) -> str:
    """
    이미지와 텍스트를 분석하여 폐기물 분류 결과를 반환

    Args:
        user_input_text: 사용자 입력 텍스트
        image_urls: 분석할 이미지 URL 리스트

    Returns:
        분류 결과 JSON 문자열:
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
    system_prompt = raw_prompt.replace("{{ITEM_CLASS_YAML}}", item_class_text).replace(
        "{{SITUATION_TAG_YAML}}", situation_tags_text
    )

    content_items = []
    system_items = []

    # 시스템 메시지 구성
    system_items.append(
        {
            "type": "input_text",
            "text": "아래는 item_class_list.yaml 내용입니다:\n\n" + item_class_text,
        }
    )

    system_items.append(
        {
            "type": "input_text",
            "text": "아래는 situation_tags.yaml 내용입니다:\n\n" + situation_tags_text,
        }
    )

    system_items.append({"type": "input_text", "text": system_prompt})

    # 사용자 메시지 구성
    content_items.append({"type": "input_text", "text": user_input_text})

    # 이미지 추가
    for url in image_urls:
        content_items.append(
            {
                "type": "input_image",
                "image_url": {
                    "url": url,
                },
            }
        )

    # Vision API 호출
    response = client.responses.create(
        model="gpt-5.1",
        input=[
            {
                "role": "system",
                "content": system_items,
            },
            {
                "role": "user",
                "content": content_items,
            },
        ],
    )

    return response.output_text
