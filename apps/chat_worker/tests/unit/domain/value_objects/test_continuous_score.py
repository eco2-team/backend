"""ContinuousScore Value Object Unit Tests."""

from __future__ import annotations

import pytest

from chat_worker.domain.exceptions.eval_exceptions import InvalidContinuousScoreError
from chat_worker.domain.value_objects.continuous_score import ContinuousScore


@pytest.mark.eval_unit
class TestContinuousScore:
    """ContinuousScore Value Object 테스트."""

    def test_valid_creation(self) -> None:
        """유효한 값으로 생성."""
        score = ContinuousScore(
            value=75.0,
            information_loss=9.61,
            grade_confidence=5.0,
        )

        assert score.value == 75.0
        assert score.information_loss == 9.61
        assert score.grade_confidence == 5.0

    def test_below_zero_raises(self) -> None:
        """value < 0은 도메인 예외 발생."""
        with pytest.raises(InvalidContinuousScoreError):
            ContinuousScore(
                value=-0.1,
                information_loss=9.61,
                grade_confidence=5.0,
            )

    def test_above_100_raises(self) -> None:
        """value > 100은 도메인 예외 발생."""
        with pytest.raises(InvalidContinuousScoreError):
            ContinuousScore(
                value=100.1,
                information_loss=9.61,
                grade_confidence=5.0,
            )

    def test_boundary_zero(self) -> None:
        """경계값 0.0 허용."""
        score = ContinuousScore(
            value=0.0,
            information_loss=9.61,
            grade_confidence=0.0,
        )

        assert score.value == 0.0

    def test_boundary_100(self) -> None:
        """경계값 100.0 허용."""
        score = ContinuousScore(
            value=100.0,
            information_loss=9.61,
            grade_confidence=10.0,
        )

        assert score.value == 100.0

    def test_negative_information_loss_raises(self) -> None:
        """information_loss < 0은 도메인 예외 발생."""
        with pytest.raises(InvalidContinuousScoreError, match="information_loss"):
            ContinuousScore(
                value=50.0,
                information_loss=-1.0,
                grade_confidence=5.0,
            )

    def test_negative_grade_confidence_raises(self) -> None:
        """grade_confidence < 0은 도메인 예외 발생."""
        with pytest.raises(InvalidContinuousScoreError, match="grade_confidence"):
            ContinuousScore(
                value=50.0,
                information_loss=9.61,
                grade_confidence=-0.1,
            )

    def test_to_dict(self) -> None:
        """딕셔너리 변환."""
        score = ContinuousScore(
            value=82.5,
            information_loss=9.61,
            grade_confidence=7.5,
        )

        d = score.to_dict()

        assert d["value"] == 82.5
        assert d["information_loss"] == 9.61
        assert d["grade_confidence"] == 7.5

    def test_from_dict(self) -> None:
        """딕셔너리에서 ContinuousScore 생성."""
        data = {
            "value": 60.0,
            "information_loss": 9.61,
            "grade_confidence": 5.0,
        }

        score = ContinuousScore.from_dict(data)

        assert score.value == 60.0
        assert score.information_loss == 9.61
        assert score.grade_confidence == 5.0

    def test_frozen(self) -> None:
        """불변성 테스트 (frozen dataclass)."""
        score = ContinuousScore(
            value=50.0,
            information_loss=9.61,
            grade_confidence=5.0,
        )

        with pytest.raises(AttributeError):
            score.value = 80.0  # type: ignore
