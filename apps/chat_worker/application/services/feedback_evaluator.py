"""Feedback Evaluator Service - Rule 기반 품질 평가.

순수 비즈니스 로직만 포함. Port 의존성 없음.
LLM 기반 평가가 필요하면 Node(UseCase)에서 조립.

Clean Architecture:
- Service: 이 파일 (순수 비즈니스 로직)
- Port: feedback/ports/llm_evaluator.py (LLM 평가 추상화)
- UseCase: nodes/feedback_node.py (Service + Port 조립)
"""

from __future__ import annotations

import logging
from typing import Any

from chat_worker.application.dto.feedback_result import FeedbackResult
from chat_worker.domain.enums import FallbackReason, FeedbackQuality

logger = logging.getLogger(__name__)


class FeedbackEvaluatorService:
    """RAG 품질 평가 서비스 (Rule 기반).

    순수 비즈니스 로직만 포함:
    - Rule 기반 빠른 평가
    - Fallback 필요 여부 판단

    LLM 기반 정밀 평가는 Node에서 별도로 호출.
    """

    def evaluate_by_rules(
        self,
        query: str,
        rag_results: dict[str, Any] | None,
    ) -> FeedbackResult:
        """규칙 기반 품질 평가.

        평가 기준:
        1. 결과 존재 여부 (0.3)
        2. 카테고리 매칭 (0.2)
        3. 정보 풍부도 (0.2)
        4. 키워드 매칭 (0.3)

        Args:
            query: 사용자 질문
            rag_results: RAG 검색 결과

        Returns:
            FeedbackResult: 규칙 기반 평가 결과
        """
        # 결과 없음
        if not rag_results:
            return FeedbackResult.no_result()

        score = 0.0
        suggestions: list[str] = []
        metadata: dict[str, Any] = {}

        # 1. 데이터 존재 여부 (기본 0.3)
        data = rag_results.get("data", {})
        if data:
            score += 0.3
            metadata["has_data"] = True
        else:
            suggestions.append("검색 데이터 없음")
            return FeedbackResult.from_score(0.1, suggestions, metadata)

        # 2. 카테고리 매칭 (0.2)
        category = rag_results.get("category", "")
        if category:
            score += 0.2
            metadata["category"] = category

        # 3. 세부 정보 풍부도 (0.2)
        disposal_info = data.get("disposal_info", [])
        if disposal_info and len(disposal_info) > 0:
            score += 0.2
            metadata["disposal_info_count"] = len(disposal_info)

        # 4. 키워드 매칭 (0.3)
        query_keywords = set(query.lower().split())
        content_str = str(data).lower()
        matched_keywords = sum(1 for kw in query_keywords if kw in content_str)
        keyword_ratio = matched_keywords / max(len(query_keywords), 1)
        score += 0.3 * keyword_ratio
        metadata["keyword_match_ratio"] = keyword_ratio

        # 품질 등급 결정
        if score < 0.4:
            suggestions.append("키워드 매칭률 낮음")
            suggestions.append("웹 검색으로 보완 권장")

        logger.debug(
            "Rule-based evaluation",
            extra={
                "query": query[:50],
                "score": score,
                "quality": FeedbackQuality.from_score(score).value,
            },
        )

        return FeedbackResult.from_score(score, suggestions, metadata)

    def should_use_fallback(
        self,
        feedback: FeedbackResult,
        intent: str,
    ) -> tuple[bool, FallbackReason | None]:
        """Fallback 사용 여부 결정.

        Args:
            feedback: 품질 평가 결과
            intent: 현재 Intent

        Returns:
            (Fallback 필요 여부, 사유)
        """
        # waste Intent에서 RAG 실패 시 web_search로 Fallback
        if intent == "waste" and feedback.needs_fallback:
            return True, feedback.fallback_reason

        # 명시적으로 Fallback 필요
        if feedback.needs_fallback:
            return True, feedback.fallback_reason

        return False, None

    def needs_llm_evaluation(self, rule_result: FeedbackResult) -> bool:
        """LLM 기반 정밀 평가가 필요한지 판단.

        Rule 기반으로 GOOD 이상이면 LLM 평가 불필요.

        Args:
            rule_result: Rule 기반 평가 결과

        Returns:
            LLM 평가 필요 여부
        """
        return rule_result.quality not in (
            FeedbackQuality.EXCELLENT,
            FeedbackQuality.GOOD,
        )
