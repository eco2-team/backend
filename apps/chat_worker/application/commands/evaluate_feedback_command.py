"""Evaluate Feedback Command.

RAG 품질 평가 및 Fallback UseCase.

Clean Architecture:
- Command(UseCase): 이 파일 - 정책/흐름 담당
- Service: FeedbackEvaluatorService - 순수 비즈니스 로직
- Port: LLMFeedbackEvaluatorPort, WebSearchPort - 외부 의존
- Node(Adapter): feedback_node.py - LangGraph 어댑터

논문 참조:
- "What Makes Large Language Models Reason in (Multi-Turn) Code Generation?"
  피드백 기반 반복 개선 패턴
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from chat_worker.application.dto.fallback_result import FallbackResult
from chat_worker.application.dto.feedback_result import FeedbackResult
from chat_worker.application.services.feedback_evaluator import FeedbackEvaluatorService

if TYPE_CHECKING:
    from chat_worker.application.ports.llm_evaluator import LLMFeedbackEvaluatorPort
    from chat_worker.application.ports.web_search import WebSearchPort
    from chat_worker.application.services.fallback_orchestrator import (
        FallbackOrchestrator,
    )

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EvaluateFeedbackInput:
    """Command 입력 DTO."""

    job_id: str
    query: str
    intent: str
    rag_results: dict[str, Any] | None


@dataclass
class EvaluateFeedbackOutput:
    """Command 출력 DTO.

    도메인 이벤트를 포함하여 Node(Adapter)에서 UX 처리 가능.
    """

    feedback: FeedbackResult
    fallback_result: FallbackResult | None = None
    fallback_executed: bool = False
    events: list[str] = field(default_factory=list)

    @property
    def needs_fallback(self) -> bool:
        """Fallback이 실행되었는지."""
        return self.fallback_executed

    @property
    def final_quality_score(self) -> float:
        """최종 품질 점수."""
        return self.feedback.score


class EvaluateFeedbackCommand:
    """RAG 품질 평가 및 Fallback Command (UseCase).

    정책/흐름:
    1. Rule 기반 빠른 평가 (항상)
    2. 필요시 LLM 정밀 평가 (조건부)
    3. Fallback 필요 여부 판단
    4. 필요시 Fallback 체인 실행

    Port 주입:
    - llm_evaluator: 선택적 LLM 정밀 평가
    - web_search_client: Fallback용 웹 검색
    """

    def __init__(
        self,
        fallback_orchestrator: "FallbackOrchestrator",
        llm_evaluator: "LLMFeedbackEvaluatorPort | None" = None,
        web_search_client: "WebSearchPort | None" = None,
    ) -> None:
        """Command 초기화.

        Args:
            fallback_orchestrator: Fallback 실행 오케스트레이터
            llm_evaluator: LLM 기반 평가기 (선택)
            web_search_client: 웹 검색 클라이언트 (선택)
        """
        self._feedback_service = FeedbackEvaluatorService()
        self._fallback_orchestrator = fallback_orchestrator
        self._llm_evaluator = llm_evaluator
        self._web_search = web_search_client

    async def execute(
        self,
        input_dto: EvaluateFeedbackInput,
    ) -> EvaluateFeedbackOutput:
        """Command 실행.

        Args:
            input_dto: 입력 DTO

        Returns:
            출력 DTO (feedback + fallback 결과 + 도메인 이벤트)
        """
        events: list[str] = []

        # 1. Rule 기반 빠른 평가 (Service 호출)
        feedback = self._feedback_service.evaluate_by_rules(
            query=input_dto.query,
            rag_results=input_dto.rag_results,
        )
        events.append("rule_evaluation_completed")

        logger.info(
            "Rule-based feedback evaluated",
            extra={
                "job_id": input_dto.job_id,
                "quality": feedback.quality.value,
                "score": feedback.score,
            },
        )

        # 2. LLM 정밀 평가 (조건부, Port 사용)
        if self._should_trigger_llm_evaluation(feedback):
            feedback, llm_event = await self._evaluate_with_llm(
                input_dto=input_dto,
                current_feedback=feedback,
            )
            events.append(llm_event)

        # 3. Fallback 필요 여부 판단 (Service 호출)
        needs_fallback, fallback_reason = self._feedback_service.should_use_fallback(
            feedback=feedback,
            intent=input_dto.intent,
        )

        # 4. Fallback 실행 (조건부)
        fallback_result = None
        if needs_fallback and fallback_reason:
            events.append("fallback_started")

            fallback_result = await self._fallback_orchestrator.execute_fallback(
                reason=fallback_reason,
                query=input_dto.query,
                state={"intent": input_dto.intent},
                web_search_client=self._web_search,
            )

            events.append(f"fallback_completed:{fallback_result.strategy_used}")

            logger.info(
                "Fallback executed",
                extra={
                    "job_id": input_dto.job_id,
                    "success": fallback_result.success,
                    "strategy": fallback_result.strategy_used,
                },
            )

        return EvaluateFeedbackOutput(
            feedback=feedback,
            fallback_result=fallback_result,
            fallback_executed=fallback_result is not None,
            events=events,
        )

    def _should_trigger_llm_evaluation(self, feedback: FeedbackResult) -> bool:
        """LLM 평가 트리거 여부 판단.

        Args:
            feedback: Rule 기반 평가 결과

        Returns:
            LLM 평가 필요 여부
        """
        return (
            self._llm_evaluator is not None
            and self._feedback_service.needs_llm_evaluation(feedback)
        )

    async def _evaluate_with_llm(
        self,
        input_dto: EvaluateFeedbackInput,
        current_feedback: FeedbackResult,
    ) -> tuple[FeedbackResult, str]:
        """LLM 정밀 평가 실행.

        Args:
            input_dto: 입력 DTO
            current_feedback: 현재 Rule 기반 평가 결과

        Returns:
            (업데이트된 feedback, 이벤트 문자열)
        """
        if not self._llm_evaluator:
            return current_feedback, "llm_evaluation_skipped"

        try:
            logger.debug("Triggering LLM evaluation for low-quality result")
            llm_feedback = await self._llm_evaluator.evaluate(
                query=input_dto.query,
                rag_results=input_dto.rag_results,
                context={"intent": input_dto.intent},
            )

            # LLM 결과가 더 좋으면 사용
            if llm_feedback.score > current_feedback.score:
                logger.info(
                    "LLM evaluation improved score",
                    extra={
                        "rule_score": current_feedback.score,
                        "llm_score": llm_feedback.score,
                    },
                )
                return llm_feedback, "llm_evaluation_improved"

            return current_feedback, "llm_evaluation_no_improvement"

        except Exception as e:
            logger.warning(f"LLM evaluation failed, using rule result: {e}")
            return current_feedback, "llm_evaluation_failed"
