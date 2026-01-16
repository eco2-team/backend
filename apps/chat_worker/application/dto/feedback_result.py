"""Feedback Result DTO.

RAG 품질 평가 결과를 담는 Data Transfer Object.
Phase 1-4 적용: Citation, Nugget, Groundedness, NextSteps.

참조: docs/foundations/27-rag-evaluation-strategy.md
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from chat_worker.domain.enums import FallbackReason, FeedbackQuality


@dataclass
class EvidenceItem:
    """검색 결과 근거 항목 (Phase 1: Citation).

    Anthropic CitationAgent 패턴 적용.
    """

    chunk_id: str
    relevance: Literal["high", "medium", "low"]
    quoted_text: str = ""
    covers_nuggets: list[str] = field(default_factory=list)


@dataclass
class NuggetItem:
    """필수 정보 단위 (Phase 2: Nugget 기반 완전성).

    TREC RAG Track AutoNuggetizer 패턴 적용.
    """

    id: str
    description: str
    covered: bool = False


@dataclass
class GroundednessEvidence:
    """Groundedness 근거 (Phase 3: Groundedness 분리).

    RAGAS Faithfulness 패턴 적용.
    """

    claim: str
    source_chunk_id: str
    supported: bool = True


@dataclass
class NextStepSuggestion:
    """다음 단계 제안 (Phase 4: Just-in-Time Context).

    Anthropic Context Engineering 패턴 적용.
    """

    type: Literal["additional_retrieval", "clarification", "none"]
    urgency: Literal["immediate", "deferred", "optional"]
    query: str = ""
    reason: str = ""


@dataclass
class RetrievalQuality:
    """Retrieval 품질 평가 결과."""

    context_relevance: float = 0.0
    evidence: list[EvidenceItem] = field(default_factory=list)


@dataclass
class CompletenessResult:
    """완전성 평가 결과 (Nugget 기반)."""

    required_nuggets: list[NuggetItem] = field(default_factory=list)
    coverage_ratio: float = 0.0
    missing_nuggets: list[str] = field(default_factory=list)


@dataclass
class AnswerQuality:
    """답변 품질 평가 결과."""

    groundedness: float = 0.0
    groundedness_evidence: list[GroundednessEvidence] = field(default_factory=list)
    hallucination_risk: Literal["none", "low", "medium", "high"] = "none"


@dataclass
class NextSteps:
    """다음 단계 정보."""

    action_required: bool = False
    suggestions: list[NextStepSuggestion] = field(default_factory=list)


@dataclass
class Confidence:
    """평가 신뢰도."""

    overall: float = 0.8
    low_confidence_areas: list[str] = field(default_factory=list)


@dataclass
class FeedbackResult:
    """RAG 품질 평가 결과 (Phase 1-4 통합).

    Attributes:
        quality: 품질 등급
        score: 품질 점수 (0.0 ~ 1.0)
        needs_fallback: Fallback 필요 여부
        fallback_reason: Fallback 사유 (필요한 경우)
        suggestions: 개선 제안 목록 (legacy, next_steps로 대체 권장)
        metadata: 추가 메타데이터

        # Phase 1-4 확장 필드
        retrieval_quality: Retrieval 품질 (Evidence 포함)
        completeness: Nugget 기반 완전성
        answer_quality: Groundedness 분리된 답변 품질
        next_steps: 구체적인 다음 행동
        confidence: 평가 신뢰도
    """

    quality: FeedbackQuality
    score: float
    needs_fallback: bool = False
    fallback_reason: FallbackReason | None = None
    suggestions: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    # Phase 1-4 확장 필드
    retrieval_quality: RetrievalQuality | None = None
    completeness: CompletenessResult | None = None
    answer_quality: AnswerQuality | None = None
    next_steps: NextSteps | None = None
    confidence: Confidence | None = None

    @classmethod
    def from_score(
        cls,
        score: float,
        suggestions: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> "FeedbackResult":
        """점수에서 FeedbackResult 생성 (레거시 호환).

        Args:
            score: 품질 점수 (0.0 ~ 1.0)
            suggestions: 개선 제안 목록
            metadata: 추가 메타데이터

        Returns:
            FeedbackResult 인스턴스
        """
        quality = FeedbackQuality.from_score(score)
        needs_fallback = quality.needs_fallback()

        fallback_reason = None
        if needs_fallback:
            if score < 0.1:
                fallback_reason = FallbackReason.RAG_NO_RESULT
            else:
                fallback_reason = FallbackReason.RAG_LOW_QUALITY

        return cls(
            quality=quality,
            score=score,
            needs_fallback=needs_fallback,
            fallback_reason=fallback_reason,
            suggestions=suggestions or [],
            metadata=metadata or {},
        )

    @classmethod
    def from_evaluation(
        cls,
        overall_score: float,
        retrieval_quality: RetrievalQuality | None = None,
        completeness: CompletenessResult | None = None,
        answer_quality: AnswerQuality | None = None,
        next_steps: NextSteps | None = None,
        confidence: Confidence | None = None,
    ) -> "FeedbackResult":
        """Phase 1-4 평가 결과에서 생성.

        Args:
            overall_score: 전체 점수
            retrieval_quality: Retrieval 품질
            completeness: 완전성 결과
            answer_quality: 답변 품질
            next_steps: 다음 단계
            confidence: 신뢰도

        Returns:
            FeedbackResult 인스턴스
        """
        quality = FeedbackQuality.from_score(overall_score)
        needs_fallback = quality.needs_fallback()

        # Fallback 사유 결정 (더 정밀한 로직)
        fallback_reason = None
        if needs_fallback:
            if overall_score < 0.1:
                fallback_reason = FallbackReason.RAG_NO_RESULT
            elif completeness and completeness.coverage_ratio < 0.3:
                fallback_reason = FallbackReason.RAG_LOW_QUALITY
            elif answer_quality and answer_quality.hallucination_risk in ("medium", "high"):
                fallback_reason = FallbackReason.RAG_LOW_QUALITY
            else:
                fallback_reason = FallbackReason.RAG_LOW_QUALITY

        # Legacy suggestions 생성 (next_steps에서 추출)
        suggestions = []
        if next_steps and next_steps.suggestions:
            for sugg in next_steps.suggestions:
                if sugg.type == "additional_retrieval" and sugg.query:
                    suggestions.append(f"추가 검색: {sugg.query}")
                elif sugg.reason:
                    suggestions.append(sugg.reason)

        return cls(
            quality=quality,
            score=overall_score,
            needs_fallback=needs_fallback,
            fallback_reason=fallback_reason,
            suggestions=suggestions,
            metadata={},
            retrieval_quality=retrieval_quality,
            completeness=completeness,
            answer_quality=answer_quality,
            next_steps=next_steps,
            confidence=confidence,
        )

    @classmethod
    def no_result(cls) -> "FeedbackResult":
        """검색 결과 없음."""
        return cls(
            quality=FeedbackQuality.NONE,
            score=0.0,
            needs_fallback=True,
            fallback_reason=FallbackReason.RAG_NO_RESULT,
            suggestions=["웹 검색으로 대체 시도", "다른 키워드로 검색"],
            next_steps=NextSteps(
                action_required=True,
                suggestions=[
                    NextStepSuggestion(
                        type="additional_retrieval",
                        urgency="immediate",
                        query="",
                        reason="검색 결과가 없어 웹 검색 필요",
                    )
                ],
            ),
        )

    @classmethod
    def excellent(cls, score: float = 0.95) -> "FeedbackResult":
        """최고 품질 결과."""
        return cls(
            quality=FeedbackQuality.EXCELLENT,
            score=score,
            needs_fallback=False,
            confidence=Confidence(overall=0.95),
        )

    def get_next_query(self) -> str | None:
        """다음 검색 쿼리 추출 (Phase 4).

        Returns:
            다음 검색 쿼리 (없으면 None)
        """
        if not self.next_steps or not self.next_steps.suggestions:
            return None

        for sugg in self.next_steps.suggestions:
            if sugg.type == "additional_retrieval" and sugg.urgency == "immediate":
                return sugg.query

        return None

    def get_missing_info(self) -> list[str]:
        """누락된 정보 목록 추출 (Phase 2).

        Returns:
            누락된 Nugget 설명 목록
        """
        if not self.completeness:
            return []

        missing = []
        for nugget in self.completeness.required_nuggets:
            if not nugget.covered:
                missing.append(nugget.description)

        return missing

    def to_dict(self) -> dict[str, Any]:
        """딕셔너리 변환."""
        result = {
            "quality": self.quality.value,
            "score": self.score,
            "needs_fallback": self.needs_fallback,
            "fallback_reason": self.fallback_reason.value if self.fallback_reason else None,
            "suggestions": self.suggestions,
            "metadata": self.metadata,
        }

        # Phase 1-4 필드 추가
        if self.retrieval_quality:
            result["retrieval_quality"] = {
                "context_relevance": self.retrieval_quality.context_relevance,
                "evidence": [
                    {
                        "chunk_id": e.chunk_id,
                        "relevance": e.relevance,
                        "quoted_text": e.quoted_text,
                        "covers_nuggets": e.covers_nuggets,
                    }
                    for e in self.retrieval_quality.evidence
                ],
            }

        if self.completeness:
            result["completeness"] = {
                "required_nuggets": [
                    {"id": n.id, "description": n.description, "covered": n.covered}
                    for n in self.completeness.required_nuggets
                ],
                "coverage_ratio": self.completeness.coverage_ratio,
                "missing_nuggets": self.completeness.missing_nuggets,
            }

        if self.answer_quality:
            result["answer_quality"] = {
                "groundedness": self.answer_quality.groundedness,
                "hallucination_risk": self.answer_quality.hallucination_risk,
            }

        if self.next_steps:
            result["next_steps"] = {
                "action_required": self.next_steps.action_required,
                "suggestions": [
                    {
                        "type": s.type,
                        "urgency": s.urgency,
                        "query": s.query,
                        "reason": s.reason,
                    }
                    for s in self.next_steps.suggestions
                ],
            }

        if self.confidence:
            result["confidence"] = {
                "overall": self.confidence.overall,
                "low_confidence_areas": self.confidence.low_confidence_areas,
            }

        return result
