from __future__ import annotations

import json
from typing import Any

from .answer import generate_answer
from .rag import get_disposal_rules
from .vision import analyze_images


class PipelineError(RuntimeError):
    """Raised when any stage of the waste-classification pipeline fails."""


def process_waste_classification(
    user_input_text: str,
    image_url: str,
    *,
    save_result: bool = False,
    verbose: bool = False,
) -> dict[str, Any]:
    if not image_url:
        raise PipelineError("이미지 URL은 필수입니다.")

    from time import perf_counter

    start_total = perf_counter()

    if verbose:
        print("\n" + "=" * 50)
        print("STEP 1: 이미지 분석 및 분류")
        print("=" * 50)

    start_vision = perf_counter()
    result_payload = analyze_images(user_input_text, image_url)
    duration_vision = perf_counter() - start_vision

    if verbose:
        print(f"\n분석 결과:\n{result_payload}")

    classification_result = _to_dict(result_payload)

    if verbose:
        print("\n" + "=" * 50)
        print("STEP 2: Lite RAG - 배출 규정 매칭")
        print("=" * 50)

    start_rag = perf_counter()
    disposal_rules = get_disposal_rules(classification_result)
    if not disposal_rules:
        raise PipelineError("매칭되는 배출 규정을 찾지 못했습니다.")
    duration_rag = perf_counter() - start_rag

    if verbose:
        cls = classification_result.get("classification", {})
        print(
            f"\n✅ 배출 규정 매칭 성공: "
            f"{cls.get('major_category')} / {cls.get('middle_category')} / {cls.get('minor_category')}"
        )
        print("\n" + "=" * 50)
        print("STEP 3: 자연어 답변 생성")
        print("=" * 50)

    start_answer = perf_counter()
    final_answer = generate_answer(
        classification_result,
        disposal_rules,
        save_result=save_result,
    )
    duration_answer = perf_counter() - start_answer

    duration_total = perf_counter() - start_total

    if verbose:
        print("\n✅ 답변 생성 완료")

    return {
        "classification_result": classification_result,
        "disposal_rules": disposal_rules,
        "final_answer": final_answer,
        "metadata": {
            "duration_vision": duration_vision,
            "duration_rag": duration_rag,
            "duration_answer": duration_answer,
            "duration_total": duration_total,
        },
    }


def _to_dict(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict):
        return payload
    if isinstance(payload, str):
        try:
            return json.loads(payload)
        except json.JSONDecodeError as exc:
            raise PipelineError(f"분류 결과 파싱에 실패했습니다: {exc}") from exc
    raise PipelineError("분류 결과 형식이 올바르지 않습니다.")


def _run_cli() -> None:
    image_url = "https://i.postimg.cc/NfjDJ3Cd/image.png"
    user_input_text = "어떻게 분리수거해야하지?"

    print("\n🌱 Eco² 분리배출 AI 파이프라인 시작")
    print(f"📝 사용자 입력: {user_input_text}")
    print("🖼️  이미지 개수: 1개")

    try:
        result = process_waste_classification(
            user_input_text,
            image_url,
            save_result=True,
            verbose=True,
        )
    except PipelineError as exc:
        print(f"\n❌ 오류 발생: {exc}")
        return

    print("\n" + "=" * 50)
    print("📋 최종 결과")
    print("=" * 50)
    print(json.dumps(result["final_answer"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    _run_cli()
