"""BARS Evaluation Pydantic Schemas.

LLM Structured Output 응답 스키마.
BARSEvalOutput은 5축 BARS 평가의 JSON 응답 구조를 정의합니다.

LLMClientPort.generate_structured(schema=BARSEvalOutput) 호출 시 사용.
파싱 실패 시 retry-with-repair 루프 (최대 2회) 후 L1 fallback.

See: docs/plans/chat-eval-pipeline-plan.md §3.2.2
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class AxisEvaluation(BaseModel):
    """단일 축 BARS 평가 결과.

    Attributes:
        score: BARS 1-5점
        evidence: 근거 인용 (반드시 Retrieved Context에서 인용)
        reasoning: 채점 근거
    """

    score: int = Field(ge=1, le=5, description="BARS 1-5점")
    evidence: str = Field(
        description="근거 인용 (RULERS: 반드시 Retrieved Context에서 인용)",
    )
    reasoning: str = Field(description="채점 근거")


class BARSEvalOutput(BaseModel):
    """5축 BARS 평가 전체 결과.

    LLM Structured Output으로 파싱 보장.
    각 축은 독립적으로 1-5 BARS 스케일로 채점.

    See: docs/plans/chat-eval-pipeline-plan.md §3.2.1
    """

    faithfulness: AxisEvaluation = Field(description="사실 충실도 (가중치 0.30)")
    relevance: AxisEvaluation = Field(description="질문 관련성 (가중치 0.25)")
    completeness: AxisEvaluation = Field(description="정보 완결성 (가중치 0.20)")
    safety: AxisEvaluation = Field(description="안전성 (가중치 0.15)")
    communication: AxisEvaluation = Field(description="소통 품질 (가중치 0.10)")


class SingleAxisEvalOutput(BaseModel):
    """단일 축 BARS 평가 결과.

    Self-Consistency 트리거 시 개별 축 독립 호출용.
    """

    evaluation: AxisEvaluation = Field(description="평가 결과")


# 평가 축 이름 상수
EVAL_AXES: tuple[str, ...] = (
    "faithfulness",
    "relevance",
    "completeness",
    "safety",
    "communication",
)

__all__ = [
    "AxisEvaluation",
    "BARSEvalOutput",
    "EVAL_AXES",
    "SingleAxisEvalOutput",
]
