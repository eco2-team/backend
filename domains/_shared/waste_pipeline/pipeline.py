from __future__ import annotations

import json
from typing import Any, Sequence

from .answer import generate_answer
from .rag import get_disposal_rules
from .vision import analyze_images


class PipelineError(RuntimeError):
    """Raised when any stage of the waste-classification pipeline fails."""


def process_waste_classification(
    user_input_text: str,
    image_urls: Sequence[str],
    *,
    save_result: bool = False,
    verbose: bool = False,
) -> dict[str, Any]:
    if not image_urls:
        raise PipelineError("이미지 URL은 최소 한 개 이상이어야 합니다.")

    if verbose:
        print("\n" + "=" * 50)
        print("STEP 1: 이미지 분석 및 분류")
        print("=" * 50)

    result_text = analyze_images(user_input_text, list(image_urls))

    if verbose:
        print(f"\n분석 결과:\n{result_text}")

    try:
        classification_result = json.loads(result_text)
    except json.JSONDecodeError as exc:
        raise PipelineError(f"분류 결과 파싱에 실패했습니다: {exc}") from exc

    if verbose:
        print("\n" + "=" * 50)
        print("STEP 2: Lite RAG - 배출 규정 매칭")
        print("=" * 50)

    disposal_rules = get_disposal_rules(classification_result)
    if not disposal_rules:
        raise PipelineError("매칭되는 배출 규정을 찾지 못했습니다.")

    if verbose:
        cls = classification_result.get("classification", {})
        print(
            f"\n✅ 배출 규정 매칭 성공: "
            f"{cls.get('major_category')} / {cls.get('middle_category')} / {cls.get('minor_category')}"
        )
        print("\n" + "=" * 50)
        print("STEP 3: 자연어 답변 생성")
        print("=" * 50)

    final_answer = generate_answer(
        classification_result,
        disposal_rules,
        save_result=save_result,
    )

    if verbose:
        print("\n✅ 답변 생성 완료")

    return {
        "classification_result": classification_result,
        "disposal_rules": disposal_rules,
        "final_answer": final_answer,
    }


def _run_cli() -> None:
    image_urls = [
        "https://i.postimg.cc/NfjDJ3Cd/image.png",
    ]
    user_input_text = "어떻게 분리수거해야하지?"

    print("\n🌱 Eco² 분리배출 AI 파이프라인 시작")
    print(f"📝 사용자 입력: {user_input_text}")
    print(f"🖼️  이미지 개수: {len(image_urls)}개")

    try:
        result = process_waste_classification(
            user_input_text,
            image_urls,
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
