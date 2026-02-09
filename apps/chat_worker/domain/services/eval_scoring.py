"""EvalScoringService Domain Service.

순수 비즈니스 로직: 다축 BARS 점수를 연속 점수로 산출하는 규칙.
외부 의존성 없음.
"""

import math
from typing import ClassVar

from chat_worker.domain.enums.eval_grade import EvalGrade
from chat_worker.domain.value_objects.axis_score import AxisScore
from chat_worker.domain.value_objects.continuous_score import ContinuousScore


class EvalScoringService:
    """순수 비즈니스 로직: 점수 산출 규칙. 외부 의존성 없음.

    5-Axis BARS 평가 결과를 비대칭 가중치로 합산하여
    0-100 연속 점수(ContinuousScore)를 생성합니다.

    Attributes:
        DEFAULT_WEIGHTS: 기본 가중치 (합계 1.0)
        HAZARDOUS_WEIGHTS: 위험물 intent 시 Safety 부스트 가중치
    """

    # 비대칭 가중치 (순열 충돌 방지)
    DEFAULT_WEIGHTS: ClassVar[dict[str, float]] = {
        "faithfulness": 0.30,
        "relevance": 0.25,
        "completeness": 0.20,
        "safety": 0.15,
        "communication": 0.10,
    }

    # 위험물 intent 시 Safety 가중치 동적 부스트
    HAZARDOUS_WEIGHTS: ClassVar[dict[str, float]] = {
        "faithfulness": 0.30,
        "relevance": 0.25,
        "completeness": 0.15,
        "safety": 0.25,
        "communication": 0.05,
    }

    @staticmethod
    def compute_continuous_score(
        axis_scores: dict[str, AxisScore],
        weights: dict[str, float] | None = None,
    ) -> ContinuousScore:
        """다축 BARS 점수를 연속 점수로 산출.

        Args:
            axis_scores: 축 이름 -> AxisScore 매핑
            weights: 축별 가중치 (None이면 DEFAULT_WEIGHTS 사용)

        Returns:
            ContinuousScore (value, information_loss, grade_confidence)
        """
        w = weights or EvalScoringService.DEFAULT_WEIGHTS

        # 가중 합산
        weighted_sum = sum(
            w[axis] * score.normalized for axis, score in axis_scores.items() if axis in w
        )

        # 등급 결정
        grade = EvalGrade.from_continuous_score(weighted_sum)

        # 정보 손실: 5^5 = 3125 combinations -> 4 grades
        input_bits = 5 * math.log2(5)  # 11.61 bits
        output_bits = math.log2(4)  # 2.0 bits
        info_loss = input_bits - output_bits  # 9.61 bits

        # 등급 경계까지 거리
        lower, upper = grade.grade_boundaries
        boundary_dist = min(
            abs(weighted_sum - lower),
            abs(weighted_sum - upper),
        )

        return ContinuousScore(
            value=round(weighted_sum, 2),
            information_loss=round(info_loss, 2),
            grade_confidence=round(boundary_dist, 2),
        )
