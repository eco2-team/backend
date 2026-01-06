"""Pipeline Result Value Object."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class PipelineResult:
    """파이프라인 실행 결과 Value Object.

    4단계 파이프라인 (Vision → Rule → Answer → Reward) 결과 집합.

    Attributes:
        classification_result: Vision 분류 결과
        disposal_rules: RAG 배출 규정 검색 결과
        final_answer: 최종 답변 생성 결과
    """

    classification_result: dict[str, Any] = field(default_factory=dict)
    disposal_rules: dict[str, Any] | None = None
    final_answer: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PipelineResult:
        """딕셔너리에서 PipelineResult 생성."""
        return cls(
            classification_result=data.get("classification_result", {}),
            disposal_rules=data.get("disposal_rules"),
            final_answer=data.get("final_answer", {}),
        )

    def to_dict(self) -> dict[str, Any]:
        """딕셔너리로 변환 (API 응답용)."""
        return {
            "classification_result": self.classification_result,
            "disposal_rules": self.disposal_rules,
            "final_answer": self.final_answer,
        }

    @property
    def has_disposal_rules(self) -> bool:
        """배출 규정이 있는지 확인."""
        return self.disposal_rules is not None and bool(self.disposal_rules)

    @property
    def has_insufficiencies(self) -> bool:
        """답변에 부족한 점이 있는지 확인."""
        insufficiencies = self.final_answer.get("insufficiencies", [])
        return any(isinstance(entry, str) and entry.strip() for entry in insufficiencies)
