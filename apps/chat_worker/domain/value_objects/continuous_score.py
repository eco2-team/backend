"""ContinuousScore Value Object.

0-100 연속 점수를 표현하는 불변 객체입니다.
정보 손실 추적을 포함합니다.
"""

from dataclasses import dataclass

from chat_worker.domain.exceptions.eval_exceptions import InvalidContinuousScoreError


@dataclass(frozen=True, slots=True)
class ContinuousScore:
    """0-100 연속 점수 (Immutable).

    다축 BARS 평가를 단일 연속 점수로 압축한 결과입니다.
    정보 손실량과 등급 경계까지의 거리를 함께 추적합니다.

    Attributes:
        value: 0-100 범위의 연속 점수
        information_loss: 정보 손실량 (bits)
        grade_confidence: 가장 가까운 등급 경계까지의 거리
    """

    value: float
    information_loss: float
    grade_confidence: float

    def __post_init__(self) -> None:
        """Validation."""
        if not 0.0 <= self.value <= 100.0:
            raise InvalidContinuousScoreError(f"Score must be 0-100, got {self.value}")
        if self.information_loss < 0.0:
            raise InvalidContinuousScoreError(
                f"information_loss must be >= 0, got {self.information_loss}"
            )
        if self.grade_confidence < 0.0:
            raise InvalidContinuousScoreError(
                f"grade_confidence must be >= 0, got {self.grade_confidence}"
            )

    def to_dict(self) -> dict:
        """딕셔너리로 변환."""
        return {
            "value": self.value,
            "information_loss": self.information_loss,
            "grade_confidence": self.grade_confidence,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ContinuousScore":
        """딕셔너리에서 ContinuousScore 생성.

        Args:
            data: value, information_loss, grade_confidence 키를 포함하는 딕셔너리

        Returns:
            ContinuousScore 인스턴스
        """
        return cls(
            value=data["value"],
            information_loss=data["information_loss"],
            grade_confidence=data["grade_confidence"],
        )
