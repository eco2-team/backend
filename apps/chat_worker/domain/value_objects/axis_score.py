"""AxisScore Value Object.

단일 평가축의 BARS 채점 결과를 표현하는 불변 객체입니다.
"""

from dataclasses import dataclass

from chat_worker.domain.exceptions import InvalidBARSScoreError


@dataclass(frozen=True, slots=True)
class AxisScore:
    """단일 평가축의 BARS 채점 결과 (Immutable).

    LLM Grader의 5-Axis BARS Rubric 평가에서
    각 축의 채점 결과를 캡슐화합니다.

    Attributes:
        axis: 평가축 이름 (e.g. "faithfulness")
        score: BARS 1-5점
        evidence: 근거 인용 (Retrieved Context에서 인용, RULERS)
        reasoning: 채점 근거
    """

    axis: str
    score: int
    evidence: str
    reasoning: str

    def __post_init__(self) -> None:
        """Validation."""
        if not 1 <= self.score <= 5:
            raise InvalidBARSScoreError(f"BARS score must be 1-5, got {self.score}")
        if not self.evidence.strip():
            raise InvalidBARSScoreError("Evidence must not be empty (RULERS)")

    @property
    def normalized(self) -> float:
        """0-100 정규화.

        Returns:
            0.0 ~ 100.0 범위의 정규화된 점수
        """
        return (self.score - 1) / 4.0 * 100

    def to_dict(self) -> dict:
        """딕셔너리로 변환."""
        return {
            "axis": self.axis,
            "score": self.score,
            "evidence": self.evidence,
            "reasoning": self.reasoning,
            "normalized": self.normalized,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AxisScore":
        """딕셔너리에서 AxisScore 생성.

        Args:
            data: axis, score, evidence, reasoning 키를 포함하는 딕셔너리

        Returns:
            AxisScore 인스턴스
        """
        return cls(
            axis=data["axis"],
            score=data["score"],
            evidence=data["evidence"],
            reasoning=data["reasoning"],
        )
