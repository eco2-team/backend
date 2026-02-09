"""EvalGrade Enum Unit Tests."""

from __future__ import annotations

import pytest

from chat_worker.domain.enums.eval_grade import EvalGrade


@pytest.mark.eval_unit
class TestEvalGrade:
    """EvalGrade Enum 테스트."""

    def test_values(self) -> None:
        """모든 등급 값 확인."""
        assert EvalGrade.S.value == "S"
        assert EvalGrade.A.value == "A"
        assert EvalGrade.B.value == "B"
        assert EvalGrade.C.value == "C"

    def test_from_continuous_score_s(self) -> None:
        """연속 점수 >= 90 → S등급."""
        assert EvalGrade.from_continuous_score(95.0) == EvalGrade.S
        assert EvalGrade.from_continuous_score(100.0) == EvalGrade.S

    def test_from_continuous_score_a(self) -> None:
        """연속 점수 75-89 → A등급."""
        assert EvalGrade.from_continuous_score(80.0) == EvalGrade.A
        assert EvalGrade.from_continuous_score(89.0) == EvalGrade.A

    def test_from_continuous_score_b(self) -> None:
        """연속 점수 55-74 → B등급."""
        assert EvalGrade.from_continuous_score(60.0) == EvalGrade.B
        assert EvalGrade.from_continuous_score(74.0) == EvalGrade.B

    def test_from_continuous_score_c(self) -> None:
        """연속 점수 < 55 → C등급."""
        assert EvalGrade.from_continuous_score(54.0) == EvalGrade.C
        assert EvalGrade.from_continuous_score(0.0) == EvalGrade.C
        assert EvalGrade.from_continuous_score(30.0) == EvalGrade.C

    def test_boundary_90(self) -> None:
        """경계값 정확히 90 → S등급."""
        assert EvalGrade.from_continuous_score(90.0) == EvalGrade.S

    def test_boundary_75(self) -> None:
        """경계값 정확히 75 → A등급."""
        assert EvalGrade.from_continuous_score(75.0) == EvalGrade.A

    def test_boundary_55(self) -> None:
        """경계값 정확히 55 → B등급."""
        assert EvalGrade.from_continuous_score(55.0) == EvalGrade.B

    def test_from_string_valid(self) -> None:
        """유효한 문자열에서 생성."""
        assert EvalGrade.from_string("S") == EvalGrade.S
        assert EvalGrade.from_string("A") == EvalGrade.A
        assert EvalGrade.from_string("B") == EvalGrade.B
        assert EvalGrade.from_string("C") == EvalGrade.C

    def test_from_string_invalid_returns_c(self) -> None:
        """유효하지 않은 문자열은 C 반환."""
        assert EvalGrade.from_string("X") == EvalGrade.C
        assert EvalGrade.from_string("invalid") == EvalGrade.C
        assert EvalGrade.from_string("") == EvalGrade.C

    def test_from_string_case_insensitive(self) -> None:
        """대소문자 구분 없이 변환."""
        assert EvalGrade.from_string("s") == EvalGrade.S
        assert EvalGrade.from_string("a") == EvalGrade.A
        assert EvalGrade.from_string("b") == EvalGrade.B
        assert EvalGrade.from_string("c") == EvalGrade.C

    def test_needs_regeneration_c_true(self) -> None:
        """C등급은 재생성 필요."""
        assert EvalGrade.C.needs_regeneration is True

    def test_needs_regeneration_others_false(self) -> None:
        """S, A, B등급은 재생성 불필요."""
        assert EvalGrade.S.needs_regeneration is False
        assert EvalGrade.A.needs_regeneration is False
        assert EvalGrade.B.needs_regeneration is False

    def test_grade_boundaries(self) -> None:
        """등급 경계 튜플 확인 (반개구간 [lower, upper))."""
        assert EvalGrade.S.grade_boundaries == (90.0, 100.0)
        assert EvalGrade.A.grade_boundaries == (75.0, 90.0)
        assert EvalGrade.B.grade_boundaries == (55.0, 75.0)
        assert EvalGrade.C.grade_boundaries == (0.0, 55.0)
