from __future__ import annotations

import json
from typing import Any, Dict

import yaml

from .answer import generate_answer
from .rag import get_disposal_rules
from .utils import (
    ITEM_CLASS_PATH,
    TEXT_CLASSIFICATION_PROMPT_PATH,
    get_openai_client,
    load_prompt,
    load_yaml,
    save_json_result,
)

# ==========================================
# YAML 데이터 로드 및 변환
# ==========================================
_item_class_yaml = load_yaml(ITEM_CLASS_PATH)
_item_class_text = yaml.dump(_item_class_yaml, allow_unicode=True)


# ==========================================
# GPT-5.1를 사용한 텍스트 기반 분류
# ==========================================
def classify_text(user_input_text: str, *, save_result: bool = False) -> str:
    """
    텍스트만으로 폐기물 분류 결과를 반환합니다.
    """

    client = get_openai_client()

    raw_prompt = load_prompt(TEXT_CLASSIFICATION_PROMPT_PATH)
    system_prompt = raw_prompt.replace("{{ITEM_CLASS_YAML}}", _item_class_text)

    response = client.chat.completions.create(
        model="gpt-5.1",
        messages=[
            {
                "role": "system",
                "content": system_prompt,
            },
            {
                "role": "user",
                "content": user_input_text,
            },
        ],
    )

    result_text = response.choices[0].message.content if response.choices else ""
    if not result_text:
        raise RuntimeError("텍스트 분류 결과를 가져오지 못했습니다.")

    if save_result:
        try:
            parsed = json.loads(result_text)
        except json.JSONDecodeError:
            print("⚠️  텍스트 분류 결과 저장 실패: JSON 파싱 오류")
        else:
            save_json_result(parsed, "text_classification")

    return result_text


# ==========================================
# 텍스트 기반 파이프라인 실행 함수
# ==========================================
def process_text_classification(
    user_input_text: str,
    *,
    save_results: bool = True,
    verbose: bool = False,
) -> Dict[str, Any]:
    """
    텍스트 기반 폐기물 분리배출 안내 전체 파이프라인 실행.

    Returns a dict with classification, disposal rules, and final answer.
    """

    if verbose:
        print("\n" + "=" * 50)
        print("STEP 1: 텍스트 분석 및 분류")
        print("=" * 50)

    result_text = classify_text(user_input_text, save_result=save_results)

    if verbose:
        print(f"\n분석 결과:\n{result_text}")

    try:
        classification_result = json.loads(result_text)
    except json.JSONDecodeError as exc:
        print(f"\n❌ JSON 파싱 오류: {exc}")
        return {"error": "JSON 파싱 실패", "raw_result": result_text}

    if verbose:
        print("\n" + "=" * 50)
        print("STEP 2: Lite RAG - 배출 규정 매칭")
        print("=" * 50)

    disposal_rules = get_disposal_rules(classification_result)
    if not disposal_rules:
        if verbose:
            print("\n⚠️  매칭된 배출 규정을 찾을 수 없습니다. 분류 결과만으로 답변을 생성합니다.")
        disposal_rules = {}
    elif verbose:
        classification = classification_result.get("classification", {})
        print(
            f"\n✅ 배출 규정 매칭 성공\n"
            f"대분류: {classification.get('major_category')}\n"
            f"중분류: {classification.get('middle_category')}\n"
            f"소분류: {classification.get('minor_category')}"
        )

    if verbose:
        print("\n" + "=" * 50)
        print("STEP 3: 자연어 답변 생성")
        print("=" * 50)

    final_answer = generate_answer(
        classification_result,
        disposal_rules,
        save_result=save_results,
    )

    if verbose:
        print("\n✅ 답변 생성 완료")

    return {
        "classification_result": classification_result,
        "disposal_rules": disposal_rules,
        "final_answer": final_answer,
    }
