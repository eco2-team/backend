"""LLM-based Feedback Evaluator.

LLM을 사용하여 RAG 결과의 품질을 의미적으로 평가합니다.
Phase 1-4 적용: Citation, Nugget, Groundedness, NextSteps.

Clean Architecture:
- Adapter: 이 파일 (구현체, Infrastructure Layer)
- Port: application/ports/llm_evaluator.py (추상화, Application Layer)

참조: docs/foundations/27-rag-evaluation-strategy.md
"""

from __future__ import annotations

import json
import logging
import re
from typing import TYPE_CHECKING, Any

from chat_worker.application.dto.feedback_result import (
    AnswerQuality,
    CompletenessResult,
    Confidence,
    EvidenceItem,
    FeedbackResult,
    GroundednessEvidence,
    NextSteps,
    NextStepSuggestion,
    NuggetItem,
    RetrievalQuality,
)
from chat_worker.application.ports.llm_evaluator import LLMFeedbackEvaluatorPort
from chat_worker.infrastructure.assets.prompt_loader import load_prompt_file

if TYPE_CHECKING:
    from chat_worker.application.ports.llm import LLMClientPort

logger = logging.getLogger(__name__)


class LLMFeedbackEvaluator(LLMFeedbackEvaluatorPort):
    """LLM 기반 RAG 품질 평가기 (Phase 1-4 적용).

    LLM을 사용하여 의미적 품질 평가를 수행합니다.
    비용이 발생하므로 Rule 기반 평가 후 필요할 때만 사용합니다.

    Phase 1: Citation 기반 근거 추적
    Phase 2: Nugget 기반 완전성 측정
    Phase 3: Groundedness/Faithfulness 분리
    Phase 4: Just-in-Time Context (구체적 next_queries)
    """

    def __init__(self, llm_client: "LLMClientPort") -> None:
        """초기화.

        Args:
            llm_client: LLM 클라이언트
        """
        self._llm = llm_client
        self._evaluation_prompt = load_prompt_file("evaluation", "feedback_evaluation")
        self._relevance_prompt = load_prompt_file("evaluation", "answer_relevance")

    async def evaluate(
        self,
        query: str,
        rag_results: dict[str, Any] | None,
        context: dict[str, Any] | None = None,
    ) -> FeedbackResult:
        """RAG 결과 품질 평가 (Phase 1-4 통합).

        Args:
            query: 사용자 질문
            rag_results: RAG 검색 결과
            context: 추가 컨텍스트 (evidence 포함 시 개별 chunk로 분리)

        Returns:
            FeedbackResult: Phase 1-4 필드가 포함된 품질 평가 결과
        """
        if not rag_results:
            return FeedbackResult.no_result()

        try:
            # XML Context 형식으로 RAG 결과 포맷팅
            rag_context = self._format_rag_as_xml_context(rag_results, context)

            prompt = self._evaluation_prompt.format(
                query=query,
                rag_results=rag_context,
            )

            response = await self._llm.generate(
                prompt=prompt,
                temperature=0.1,  # 일관된 평가를 위해 낮은 temperature
            )

            return self._parse_phase4_response(response)

        except Exception as e:
            logger.error(f"LLM evaluation failed: {e}")
            # 실패 시 기본값 반환 (Rule 기반으로 폴백)
            return FeedbackResult.from_score(0.5, ["LLM 평가 실패, 기본값 사용"])

    async def evaluate_answer_relevance(
        self,
        query: str,
        answer: str,
        sources: list[dict[str, Any]] | None = None,
    ) -> FeedbackResult:
        """답변 관련성 평가.

        Args:
            query: 사용자 질문
            answer: 생성된 답변
            sources: 참조 소스

        Returns:
            FeedbackResult: 관련성 평가 결과
        """
        prompt = self._relevance_prompt.format(query=query, answer=answer)

        try:
            response = await self._llm.generate(prompt=prompt, temperature=0.1)
            return self._parse_relevance_response(response)
        except Exception as e:
            logger.error(f"Answer relevance evaluation failed: {e}")
            return FeedbackResult.from_score(0.5)

    def _format_rag_as_xml_context(
        self,
        rag_results: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> str:
        """RAG 결과를 XML Context 형식으로 포맷팅.

        여러 chunk가 있을 경우 각각을 별도의 <context id="rag_chunk_N">으로 분리합니다.
        이렇게 하면 LLM이 각 chunk를 명확히 구분하고 chunk_id로 인용할 수 있습니다.

        Args:
            rag_results: RAG 검색 결과 (단일 또는 다중)
            context: 추가 컨텍스트 (metadata 등)

        Returns:
            XML Context 형식의 문자열
        """
        xml_parts = []

        # 메인 RAG 결과
        if isinstance(rag_results, list):
            # 다중 chunk일 경우 각각 분리
            for i, chunk in enumerate(rag_results):
                chunk_xml = f'<context id="rag_chunk_{i}">\n'
                chunk_xml += json.dumps(chunk, ensure_ascii=False, indent=2)
                chunk_xml += "\n</context>"
                xml_parts.append(chunk_xml)
        else:
            # 단일 결과일 경우
            main_xml = '<context id="rag_chunk_0">\n'
            main_xml += json.dumps(rag_results, ensure_ascii=False, indent=2)
            main_xml += "\n</context>"
            xml_parts.append(main_xml)

        # 추가 메타데이터 컨텍스트
        if context:
            meta_xml = '<context id="rag_metadata">\n'
            meta_xml += json.dumps(context, ensure_ascii=False, indent=2)
            meta_xml += "\n</context>"
            xml_parts.append(meta_xml)

        return "\n\n".join(xml_parts)

    def _parse_phase4_response(self, response: str) -> FeedbackResult:
        """Phase 1-4 평가 응답 파싱.

        Args:
            response: LLM 응답

        Returns:
            FeedbackResult: 파싱된 결과 (Phase 1-4 필드 포함)
        """
        try:
            # JSON 추출
            json_match = re.search(r"\{[\s\S]*\}", response)
            if not json_match:
                raise ValueError("No JSON found in response")

            data = json.loads(json_match.group())

            # Phase 1: Retrieval Quality (Evidence)
            retrieval_quality = self._parse_retrieval_quality(data.get("retrieval_quality"))

            # Phase 2: Completeness (Nuggets)
            completeness = self._parse_completeness(data.get("completeness"))

            # Phase 3: Answer Quality (Groundedness)
            answer_quality = self._parse_answer_quality(data.get("answer_quality"))

            # Phase 4: Next Steps
            next_steps = self._parse_next_steps(data.get("next_steps"))

            # Confidence
            confidence = self._parse_confidence(data.get("confidence"))

            # Overall score
            overall_score = data.get("overall_score", 0.5)

            return FeedbackResult.from_evaluation(
                overall_score=overall_score,
                retrieval_quality=retrieval_quality,
                completeness=completeness,
                answer_quality=answer_quality,
                next_steps=next_steps,
                confidence=confidence,
            )

        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"Failed to parse Phase 4 response: {e}, falling back to legacy")
            return self._parse_legacy_response(response)

    def _parse_retrieval_quality(self, data: dict | None) -> RetrievalQuality | None:
        """Phase 1: Retrieval Quality 파싱."""
        if not data:
            return None

        evidence = []
        for e in data.get("evidence", []):
            evidence.append(
                EvidenceItem(
                    chunk_id=e.get("chunk_id", ""),
                    relevance=e.get("relevance", "medium"),
                    quoted_text=e.get("quoted_text", ""),
                    covers_nuggets=e.get("covers_nuggets", []),
                )
            )

        return RetrievalQuality(
            context_relevance=data.get("context_relevance", 0.0),
            evidence=evidence,
        )

    def _parse_completeness(self, data: dict | None) -> CompletenessResult | None:
        """Phase 2: Completeness 파싱."""
        if not data:
            return None

        required_nuggets = []
        for n in data.get("required_nuggets", []):
            required_nuggets.append(
                NuggetItem(
                    id=n.get("id", ""),
                    description=n.get("description", ""),
                    covered=n.get("covered", False),
                )
            )

        return CompletenessResult(
            required_nuggets=required_nuggets,
            coverage_ratio=data.get("coverage_ratio", 0.0),
            missing_nuggets=data.get("missing_nuggets", []),
        )

    def _parse_answer_quality(self, data: dict | None) -> AnswerQuality | None:
        """Phase 3: Answer Quality 파싱."""
        if not data:
            return None

        groundedness_evidence = []
        for g in data.get("groundedness_evidence", []):
            groundedness_evidence.append(
                GroundednessEvidence(
                    claim=g.get("claim", ""),
                    source_chunk_id=g.get("source_chunk_id", ""),
                    supported=g.get("supported", True),
                )
            )

        return AnswerQuality(
            groundedness=data.get("groundedness", 0.0),
            groundedness_evidence=groundedness_evidence,
            hallucination_risk=data.get("hallucination_risk", "none"),
        )

    def _parse_next_steps(self, data: dict | None) -> NextSteps | None:
        """Phase 4: Next Steps 파싱."""
        if not data:
            return None

        suggestions = []
        for s in data.get("suggestions", []):
            suggestions.append(
                NextStepSuggestion(
                    type=s.get("type", "none"),
                    urgency=s.get("urgency", "optional"),
                    query=s.get("query", ""),
                    reason=s.get("reason", ""),
                )
            )

        return NextSteps(
            action_required=data.get("action_required", False),
            suggestions=suggestions,
        )

    def _parse_confidence(self, data: dict | None) -> Confidence | None:
        """Confidence 파싱."""
        if not data:
            return None

        return Confidence(
            overall=data.get("overall", 0.8),
            low_confidence_areas=data.get("low_confidence_areas", []),
        )

    def _parse_legacy_response(self, response: str) -> FeedbackResult:
        """레거시 응답 파싱 (Phase 1-4 이전 포맷).

        Args:
            response: LLM 응답

        Returns:
            FeedbackResult: 파싱된 결과
        """
        try:
            json_match = re.search(r"\{[\s\S]*\}", response)
            if not json_match:
                raise ValueError("No JSON found in response")

            data = json.loads(json_match.group())

            overall_score = data.get("overall_score", 0.5)
            suggestions = data.get("suggestions", [])
            metadata = {
                "relevance": data.get("relevance"),
                "completeness": data.get("completeness"),
                "accuracy": data.get("accuracy"),
                "explanation": data.get("explanation"),
            }

            return FeedbackResult.from_score(overall_score, suggestions, metadata)

        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"Failed to parse legacy response: {e}")
            return FeedbackResult.from_score(0.5, ["파싱 실패, 기본값 사용"])

    def _parse_relevance_response(self, response: str) -> FeedbackResult:
        """관련성 응답 파싱."""
        try:
            json_match = re.search(r"\{[\s\S]*\}", response)
            if not json_match:
                raise ValueError("No JSON found")

            data = json.loads(json_match.group())
            score = data.get("score", 0.5)
            return FeedbackResult.from_score(
                score,
                metadata={"reason": data.get("reason"), "is_relevant": data.get("is_relevant")},
            )
        except Exception:
            return FeedbackResult.from_score(0.5)
