"""EvalGrade Enum.

Eval Pipeline의 응답 품질 등급을 정의합니다.
"""

from enum import Enum


class EvalGrade(str, Enum):
    """응답 품질 등급.

    ContinuousScore(0-100)를 4단계 등급으로 매핑합니다.
    C등급 시 재생성을 트리거합니다.

    S: [90, 100] (우수)
    A: [75, 90) (양호)
    B: [55, 75) (보통)
    C: [0, 55) (미달)
    """

    S = "S"
    """우수 [90, 100]."""

    A = "A"
    """양호 [75, 90)."""

    B = "B"
    """보통 [55, 75)."""

    C = "C"
    """미달 [0, 55)."""

    @classmethod
    def from_continuous_score(cls, score: float) -> "EvalGrade":
        """연속 점수에서 등급 변환.

        Args:
            score: 0-100 범위의 연속 점수

        Returns:
            해당하는 평가 등급
        """
        if score >= 90:
            return cls.S
        if score >= 75:
            return cls.A
        if score >= 55:
            return cls.B
        return cls.C

    @classmethod
    def from_string(cls, value: str) -> "EvalGrade":
        """문자열에서 EvalGrade 생성.

        Args:
            value: 등급 문자열 (case-insensitive)

        Returns:
            매칭된 EvalGrade, 없으면 C
        """
        try:
            return cls(value.upper())
        except ValueError:
            return cls.C

    @property
    def needs_regeneration(self) -> bool:
        """재생성이 필요한지 여부."""
        return self == EvalGrade.C

    @property
    def grade_boundaries(self) -> tuple[float, float]:
        """등급 경계 (하한, 상한) 반환.

        반개구간 [lower, upper) 기준. from_continuous_score() 로직과 일치.
        grade_confidence 계산에 사용: min(|score - lower|, |score - upper|).

        Returns:
            (lower, upper) 튜플
        """
        boundaries: dict[str, tuple[float, float]] = {
            "S": (90.0, 100.0),
            "A": (75.0, 90.0),
            "B": (55.0, 75.0),
            "C": (0.0, 55.0),
        }
        return boundaries[self.value]


__all__ = ["EvalGrade"]
