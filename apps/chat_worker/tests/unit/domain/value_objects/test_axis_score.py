"""AxisScore Value Object Unit Tests."""

from __future__ import annotations

import pytest

from chat_worker.domain.exceptions import InvalidBARSScoreError
from chat_worker.domain.value_objects.axis_score import AxisScore


@pytest.mark.eval_unit
class TestAxisScore:
    """AxisScore Value Object 테스트."""

    def test_valid_creation(self) -> None:
        """유효한 BARS 점수(1-5)로 생성."""
        for score in range(1, 6):
            axis = AxisScore(
                axis="faithfulness",
                score=score,
                evidence="문서에서 인용한 근거",
                reasoning="채점 이유",
            )

            assert axis.axis == "faithfulness"
            assert axis.score == score
            assert axis.evidence == "문서에서 인용한 근거"
            assert axis.reasoning == "채점 이유"

    def test_score_below_min_raises(self) -> None:
        """score=0은 범위 위반으로 예외 발생."""
        with pytest.raises(InvalidBARSScoreError):
            AxisScore(
                axis="faithfulness",
                score=0,
                evidence="근거",
                reasoning="이유",
            )

    def test_score_above_max_raises(self) -> None:
        """score=6은 범위 위반으로 예외 발생."""
        with pytest.raises(InvalidBARSScoreError):
            AxisScore(
                axis="faithfulness",
                score=6,
                evidence="근거",
                reasoning="이유",
            )

    def test_empty_evidence_raises(self) -> None:
        """빈 evidence는 예외 발생."""
        with pytest.raises(InvalidBARSScoreError):
            AxisScore(
                axis="faithfulness",
                score=3,
                evidence="",
                reasoning="이유",
            )

    def test_whitespace_evidence_raises(self) -> None:
        """공백만 있는 evidence는 예외 발생."""
        with pytest.raises(InvalidBARSScoreError):
            AxisScore(
                axis="faithfulness",
                score=3,
                evidence="   ",
                reasoning="이유",
            )

    def test_normalized_min(self) -> None:
        """score=1일 때 정규화 점수 0.0."""
        axis = AxisScore(
            axis="faithfulness",
            score=1,
            evidence="근거",
            reasoning="이유",
        )

        assert axis.normalized == 0.0

    def test_normalized_max(self) -> None:
        """score=5일 때 정규화 점수 100.0."""
        axis = AxisScore(
            axis="faithfulness",
            score=5,
            evidence="근거",
            reasoning="이유",
        )

        assert axis.normalized == 100.0

    def test_normalized_mid(self) -> None:
        """score=3일 때 정규화 점수 50.0."""
        axis = AxisScore(
            axis="faithfulness",
            score=3,
            evidence="근거",
            reasoning="이유",
        )

        assert axis.normalized == 50.0

    def test_to_dict(self) -> None:
        """딕셔너리 변환."""
        axis = AxisScore(
            axis="relevance",
            score=4,
            evidence="관련 근거",
            reasoning="채점 근거 설명",
        )

        d = axis.to_dict()

        assert d["axis"] == "relevance"
        assert d["score"] == 4
        assert d["evidence"] == "관련 근거"
        assert d["reasoning"] == "채점 근거 설명"
        assert d["normalized"] == 75.0

    def test_from_dict(self) -> None:
        """딕셔너리에서 AxisScore 생성."""
        data = {
            "axis": "safety",
            "score": 2,
            "evidence": "안전 관련 근거",
            "reasoning": "안전 채점 이유",
        }

        axis = AxisScore.from_dict(data)

        assert axis.axis == "safety"
        assert axis.score == 2
        assert axis.evidence == "안전 관련 근거"
        assert axis.reasoning == "안전 채점 이유"

    def test_frozen(self) -> None:
        """불변성 테스트 (frozen dataclass)."""
        axis = AxisScore(
            axis="faithfulness",
            score=3,
            evidence="근거",
            reasoning="이유",
        )

        with pytest.raises(AttributeError):
            axis.score = 5  # type: ignore
