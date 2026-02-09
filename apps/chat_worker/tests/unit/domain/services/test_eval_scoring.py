"""EvalScoringService Domain Service Unit Tests."""

from __future__ import annotations

import math
import pytest

import pytest

from chat_worker.domain.services.eval_scoring import EvalScoringService
from chat_worker.domain.value_objects.axis_score import AxisScore


def _make_axis_scores(
    scores: dict[str, int],
) -> dict[str, AxisScore]:
    """테스트용 AxisScore 딕셔너리 생성 헬퍼."""
    return {
        axis: AxisScore(
            axis=axis,
            score=score,
            evidence=f"{axis} 근거",
            reasoning=f"{axis} 채점 이유",
        )
        for axis, score in scores.items()
    }


@pytest.mark.eval_unit
class TestEvalScoringService:
    """EvalScoringService 도메인 서비스 테스트."""

    def test_default_weights_sum_to_one(self) -> None:
        """기본 가중치 합계 1.0."""
        total = sum(EvalScoringService.DEFAULT_WEIGHTS.values())

        assert total == pytest.approx(1.0)

    def test_hazardous_weights_sum_to_one(self) -> None:
        """위험물 가중치 합계 1.0."""
        total = sum(EvalScoringService.HAZARDOUS_WEIGHTS.values())

        assert total == pytest.approx(1.0)

    def test_compute_all_fives(self) -> None:
        """모든 축 score=5 → 100.0."""
        axis_scores = _make_axis_scores(
            {
                "faithfulness": 5,
                "relevance": 5,
                "completeness": 5,
                "safety": 5,
                "communication": 5,
            }
        )

        result = EvalScoringService.compute_continuous_score(axis_scores)

        assert result.value == 100.0

    def test_compute_all_ones(self) -> None:
        """모든 축 score=1 → 0.0."""
        axis_scores = _make_axis_scores(
            {
                "faithfulness": 1,
                "relevance": 1,
                "completeness": 1,
                "safety": 1,
                "communication": 1,
            }
        )

        result = EvalScoringService.compute_continuous_score(axis_scores)

        assert result.value == 0.0

    def test_compute_mixed_scores(self) -> None:
        """혼합 점수 계산 검증."""
        axis_scores = _make_axis_scores(
            {
                "faithfulness": 4,  # normalized=75, weight=0.30 → 22.5
                "relevance": 3,  # normalized=50, weight=0.25 → 12.5
                "completeness": 5,  # normalized=100, weight=0.20 → 20.0
                "safety": 2,  # normalized=25, weight=0.15 → 3.75
                "communication": 4,  # normalized=75, weight=0.10 → 7.5
            }
        )

        result = EvalScoringService.compute_continuous_score(axis_scores)

        # 22.5 + 12.5 + 20.0 + 3.75 + 7.5 = 66.25
        assert result.value == pytest.approx(66.25)

    def test_custom_weights(self) -> None:
        """커스텀 가중치 적용."""
        axis_scores = _make_axis_scores(
            {
                "faithfulness": 5,  # normalized=100
                "relevance": 1,  # normalized=0
                "completeness": 1,  # normalized=0
                "safety": 1,  # normalized=0
                "communication": 1,  # normalized=0
            }
        )

        # faithfulness에 가중치 1.0, 나머지 0.0
        custom_weights = {
            "faithfulness": 1.0,
            "relevance": 0.0,
            "completeness": 0.0,
            "safety": 0.0,
            "communication": 0.0,
        }

        result = EvalScoringService.compute_continuous_score(axis_scores, weights=custom_weights)

        assert result.value == 100.0

    def test_hazardous_weights_boost_safety(self) -> None:
        """위험물 가중치에서 safety 비중 증가 확인."""
        default_safety = EvalScoringService.DEFAULT_WEIGHTS["safety"]
        hazardous_safety = EvalScoringService.HAZARDOUS_WEIGHTS["safety"]

        assert hazardous_safety > default_safety

    def test_information_loss_positive(self) -> None:
        """정보 손실량은 양수."""
        axis_scores = _make_axis_scores(
            {
                "faithfulness": 3,
                "relevance": 3,
                "completeness": 3,
                "safety": 3,
                "communication": 3,
            }
        )

        result = EvalScoringService.compute_continuous_score(axis_scores)

        assert result.information_loss > 0.0
        # 5^5 = 3125 combinations → 4 grades: 11.61 - 2.0 = 9.61 bits
        expected_loss = round(5 * math.log2(5) - math.log2(4), 2)
        assert result.information_loss == expected_loss

    def test_grade_confidence_positive(self) -> None:
        """등급 경계 거리(grade_confidence)는 양수 또는 0."""
        axis_scores = _make_axis_scores(
            {
                "faithfulness": 3,
                "relevance": 3,
                "completeness": 3,
                "safety": 3,
                "communication": 3,
            }
        )

        result = EvalScoringService.compute_continuous_score(axis_scores)

        assert result.grade_confidence >= 0.0
