"""CodeGraderService Unit Tests."""

from __future__ import annotations

import pytest

from chat_worker.application.services.eval.code_grader import (
    CodeGraderResult,
    CodeGraderService,
)


def _make_good_answer() -> str:
    """6개 슬라이스 모두 통과하는 모범 답변 생성."""
    return (
        "플라스틱 페트병의 분리배출 방법을 안내드립니다.\n\n"
        "## 분리배출 방법\n\n"
        "페트병은 내용물을 비우고, 라벨을 제거한 뒤 찌그러뜨려서 "
        "투명 페트병 전용 수거함에 배출해 주세요. "
        "뚜껑도 분리하여 플라스틱류로 배출합니다.\n\n"
        "## 주의사항\n\n"
        "- 내용물이 남아있으면 재활용이 어려울 수 있습니다.\n"
        "- 색이 있는 페트병은 일반 플라스틱으로 분류됩니다.\n\n"
        "※ 출처: 환경부 분리배출 가이드라인에 따른 안내입니다.\n"
        "자세한 내용은 환경부 홈페이지를 참고해 주세요."
    )


@pytest.mark.eval_unit
class TestCodeGraderService:
    """CodeGraderService L1 코드 기반 평가 테스트."""

    def setup_method(self) -> None:
        """테스트 초기화."""
        self.grader = CodeGraderService()

    def test_perfect_answer(self) -> None:
        """모범 답변 평가 - 모든 슬라이스 통과."""
        answer = _make_good_answer()

        result = self.grader.evaluate(answer=answer, intent="waste")

        assert result.overall_score > 0.8
        assert result.passed["format_compliance"] is True
        assert result.passed["length_check"] is True
        assert result.passed["hallucination_keywords"] is True
        assert result.passed["citation_presence"] is True

    def test_empty_answer(self) -> None:
        """빈 답변 평가."""
        result = self.grader.evaluate(answer="", intent="waste")

        assert result.scores["format_compliance"] == 0.0
        assert result.passed["format_compliance"] is False

    def test_too_short_answer(self) -> None:
        """너무 짧은 답변 평가."""
        result = self.grader.evaluate(answer="네.", intent="waste")

        assert result.passed["length_check"] is False
        assert result.scores["length_check"] < 1.0

    def test_too_long_answer(self) -> None:
        """너무 긴 답변 평가."""
        # MAX_TOKEN_COUNT=2000, 한국어 ~1.5 char/token → ~3000 chars
        answer = "가나다라마바사아자차카타파하" * 300 + "."

        result = self.grader.evaluate(answer=answer, intent="general")

        assert result.passed["length_check"] is False

    def test_hallucination_keyword_detected(self) -> None:
        """금지 표현 1건 탐지."""
        answer = "이 폐기물은 100% 안전하므로 어디에나 버려도 됩니다. " "분리배출이 필요합니다."

        result = self.grader.evaluate(answer=answer, intent="waste")

        assert result.passed["hallucination_keywords"] is False
        assert result.scores["hallucination_keywords"] < 1.0

    def test_multiple_hallucination_keywords(self) -> None:
        """금지 표현 다건 탐지 시 추가 감점."""
        answer = (
            "100% 안전하고 아무렇게나 버려도 문제없으며 "
            "확실히 보장됩니다. 분리배출 방법을 안내합니다."
        )

        result = self.grader.evaluate(answer=answer, intent="waste")

        assert result.passed["hallucination_keywords"] is False
        # 다건이므로 단건보다 더 낮은 점수
        assert result.scores["hallucination_keywords"] < 0.7

    def test_broken_markdown_code_block(self) -> None:
        """깨진 마크다운 코드 블록 감지."""
        answer = "분리배출 방법입니다.\n```python\nprint('hello')\n분리배출 주의사항."

        result = self.grader.evaluate(answer=answer, intent="waste")

        # 홀수개의 코드 블록 → 감점
        assert result.scores["format_compliance"] < 1.0

    def test_mismatched_brackets(self) -> None:
        """괄호 불일치 감지."""
        answer = "분리배출 방법 (페트병, [유리병 입니다. 환경부 가이드를 참고하세요."

        result = self.grader.evaluate(answer=answer, intent="waste")

        assert result.scores["format_compliance"] < 1.0

    def test_incomplete_sentence(self) -> None:
        """미완성 문장 감지."""
        answer = "플라스틱 페트병의 분리배출 방법은 다음과 같습니다\n분리배출을"

        result = self.grader.evaluate(answer=answer, intent="waste")

        assert result.scores["format_compliance"] < 1.0

    def test_low_korean_ratio(self) -> None:
        """한국어 비율 낮을 때 감점."""
        answer = (
            "The plastic bottle should be recycled properly. "
            "Please follow the guidelines from the EPA. "
            "Make sure to remove caps and labels before recycling. "
            "Rinse containers thoroughly to avoid contamination."
        )

        result = self.grader.evaluate(answer=answer, intent="general")

        assert result.passed["language_consistency"] is False
        assert result.scores["language_consistency"] < 1.0

    def test_waste_intent_without_citation(self) -> None:
        """waste intent에서 출처 없으면 미통과."""
        answer = (
            "플라스틱 페트병은 내용물을 비우고 라벨을 제거한 뒤 "
            "찌그러뜨려서 배출하면 됩니다. "
            "분리배출 방법을 잘 지켜주세요. "
            "주의사항으로는 뚜껑을 분리하는 것입니다."
        )

        result = self.grader.evaluate(answer=answer, intent="waste")

        assert result.passed["citation_presence"] is False
        assert result.scores["citation_presence"] == 0.0

    def test_waste_intent_with_citation(self) -> None:
        """waste intent에서 출처 있으면 통과."""
        answer = (
            "플라스틱 페트병은 내용물을 비우고 라벨을 제거한 뒤 "
            "찌그러뜨려서 배출하면 됩니다. "
            "분리배출 방법을 잘 지켜주세요. "
            "주의사항으로는 뚜껑을 분리하는 것입니다. "
            "※ 출처: 환경부 분리배출 가이드."
        )

        result = self.grader.evaluate(answer=answer, intent="waste")

        assert result.passed["citation_presence"] is True
        assert result.scores["citation_presence"] == 1.0

    def test_general_intent_no_sections_required(self) -> None:
        """general intent는 구조 제약 없음."""
        answer = "안녕하세요! 오늘 날씨가 좋네요. 도움이 필요하시면 말씀해 주세요."

        result = self.grader.evaluate(answer=answer, intent="general")

        assert result.passed["intent_answer_alignment"] is True
        assert result.scores["intent_answer_alignment"] == 1.0

    def test_overall_score_range(self) -> None:
        """overall_score는 0.0~1.0 범위."""
        # 좋은 답변
        good_result = self.grader.evaluate(answer=_make_good_answer(), intent="waste")
        assert 0.0 <= good_result.overall_score <= 1.0

        # 빈 답변
        bad_result = self.grader.evaluate(answer="", intent="waste")
        assert 0.0 <= bad_result.overall_score <= 1.0

    def test_result_to_dict_from_dict_roundtrip(self) -> None:
        """CodeGraderResult to_dict/from_dict 라운드트립."""
        result = self.grader.evaluate(answer=_make_good_answer(), intent="waste")

        d = result.to_dict()
        restored = CodeGraderResult.from_dict(d)

        assert restored.overall_score == result.overall_score
        assert restored.scores == result.scores
        assert restored.passed == result.passed
        assert restored.details == result.details
