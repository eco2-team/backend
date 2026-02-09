"""CalibrationSample Value Object.

Calibration Set의 개별 샘플을 표현하는 불변 객체입니다.
최소 2명 독립 어노테이터의 합의 결과를 포함합니다.

참조: docs/plans/chat-eval-pipeline-plan.md Section 3.3.1
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from chat_worker.domain.exceptions.eval_exceptions import (
    InvalidCalibrationSampleError,
)


@dataclass(frozen=True, slots=True)
class CalibrationSample:
    """Calibration Set 개별 샘플 (Immutable).

    Ground-truth 기반 평가 기준 이동(drift) 감지에 사용되는
    어노테이터 합의 데이터입니다.
    Cohen's kappa >= 0.0 제약 (set 포함 기준은 >= 0.6이나, VO 자체는 0.0 이상 허용).

    Attributes:
        query: 사용자 질문
        intent: 분류된 Intent (waste, general 등)
        context: RAG 컨텍스트
        reference_answer: 참조 답변 (ground-truth)
        human_scores: 어노테이터 합의 점수 {axis -> BARS 1-5 score}
        annotator_agreement: 어노테이터 간 합의도 (Cohen's kappa)
    """

    query: str
    intent: str
    context: str
    reference_answer: str
    human_scores: dict[str, int]
    annotator_agreement: float

    def __post_init__(self) -> None:
        """Validation."""
        if self.annotator_agreement < 0.0:
            raise InvalidCalibrationSampleError(
                f"Annotator agreement (Cohen's kappa) must be >= 0.0, "
                f"got {self.annotator_agreement}"
            )

    def to_dict(self) -> dict[str, Any]:
        """딕셔너리로 변환."""
        return {
            "query": self.query,
            "intent": self.intent,
            "context": self.context,
            "reference_answer": self.reference_answer,
            "human_scores": dict(self.human_scores),
            "annotator_agreement": self.annotator_agreement,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CalibrationSample:
        """딕셔너리에서 CalibrationSample 생성.

        Args:
            data: 직렬화된 CalibrationSample

        Returns:
            CalibrationSample 인스턴스
        """
        return cls(
            query=data["query"],
            intent=data["intent"],
            context=data["context"],
            reference_answer=data["reference_answer"],
            human_scores=data["human_scores"],
            annotator_agreement=data["annotator_agreement"],
        )
