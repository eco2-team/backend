"""LLM Feedback Evaluator Port - LLM 기반 품질 평가 추상화.

Clean Architecture:
- Port: 이 파일 (추상화, Application Layer)
- Adapter: infrastructure/feedback/llm_feedback_evaluator.py (구현체)

사용 위치:
- feedback_node에서 필요시 주입
- FeedbackEvaluatorService는 Rule 기반만 담당
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from chat_worker.application.dto.feedback_result import FeedbackResult


class LLMFeedbackEvaluatorPort(ABC):
    """LLM 기반 RAG 품질 평가 Port.

    Service와 분리되어 Node에서 필요시 주입됩니다.
    Rule 기반 평가로 불충분할 때 LLM으로 정밀 평가.
    """

    @abstractmethod
    async def evaluate(
        self,
        query: str,
        rag_results: dict[str, Any] | None,
        context: dict[str, Any] | None = None,
    ) -> "FeedbackResult":
        """RAG 결과 품질 평가.

        Args:
            query: 사용자 질문
            rag_results: RAG 검색 결과
            context: 추가 컨텍스트

        Returns:
            FeedbackResult: 품질 평가 결과
        """
        pass

    @abstractmethod
    async def evaluate_answer_relevance(
        self,
        query: str,
        answer: str,
        sources: list[dict[str, Any]] | None = None,
    ) -> "FeedbackResult":
        """답변 관련성 평가.

        Args:
            query: 사용자 질문
            answer: 생성된 답변
            sources: 참조 소스

        Returns:
            FeedbackResult: 관련성 평가 결과
        """
        pass
