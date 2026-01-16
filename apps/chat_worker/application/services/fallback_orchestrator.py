"""Fallback Orchestrator Service.

Fallback 체인을 관리하고 실행하는 순수 비즈니스 로직.
Port 의존 없음. Node(UseCase)에서 Port와 조립.

Fallback 체인:
1. RAG 실패 → Web Search (Port 필요)
2. Web Search 실패 → General LLM
3. Intent 불확실 → Clarification
4. Subagent 실패 → 재시도 또는 스킵

Clean Architecture:
- Service: 이 파일 (순수 비즈니스 로직)
- Port: WebSearchPort (web_search 전략에서 사용, Node에서 주입)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from chat_worker.application.dto.fallback_result import FallbackResult
from chat_worker.domain.enums import FallbackReason

if TYPE_CHECKING:
    from chat_worker.application.dto.feedback_result import (
        FeedbackResult as FeedbackResultType,
    )
    from chat_worker.application.ports.web_search import WebSearchPort

logger = logging.getLogger(__name__)

# Fallback 체인 정의
FALLBACK_CHAIN: dict[str, list[str]] = {
    "rag": ["web_search", "general_llm"],
    "web_search": ["general_llm"],
    "character": ["retry", "skip"],
    "location": ["retry", "skip"],
    "intent": ["clarify", "general"],
}

# Intent별 Clarification 메시지
CLARIFICATION_MESSAGES = {
    "waste": "어떤 물건의 분리수거 방법이 궁금하신가요? 🤔 조금 더 구체적으로 알려주시면 정확히 안내해드릴게요!",
    "location": "어떤 위치 정보가 필요하신가요? 수거함 위치, 대형폐기물 신청처 등 구체적으로 알려주세요! 📍",
    "character": "이코에 대해 더 알고 싶으신 점이 있으신가요? 무엇이든 물어보세요! 🌱",
    "general": "죄송해요, 질문을 정확히 이해하지 못했어요. 조금 더 자세히 설명해주시겠어요? 🙏",
}


class FallbackOrchestrator:
    """Fallback 체인 오케스트레이터 (순수 비즈니스 로직).

    Port 의존 없음. 외부 리소스(Web Search)는 메서드 인자로 전달.
    """

    def __init__(self, max_retries: int = 2) -> None:
        """초기화.

        Args:
            max_retries: 최대 재시도 횟수
        """
        self._max_retries = max_retries

    async def execute_fallback(
        self,
        reason: FallbackReason,
        query: str,
        state: dict[str, Any],
        web_search_client: "WebSearchPort | None" = None,
        current_strategy: str | None = None,
    ) -> FallbackResult:
        """Fallback 실행.

        Args:
            reason: Fallback 사유
            query: 사용자 질문
            state: 현재 상태
            web_search_client: 웹 검색 클라이언트 (Node에서 주입)
            current_strategy: 현재 시도 중인 전략

        Returns:
            FallbackResult: Fallback 실행 결과
        """
        strategy = self._get_next_strategy(reason, current_strategy)

        logger.info(
            "Executing fallback",
            extra={
                "reason": reason.value,
                "strategy": strategy,
                "current": current_strategy,
            },
        )

        if strategy == "web_search":
            return await self._execute_web_search_fallback(query, reason, web_search_client)
        elif strategy == "clarify":
            return self._execute_clarification_fallback(query, state, reason)
        elif strategy == "retry":
            return await self._execute_retry_fallback(state, reason)
        elif strategy == "general_llm":
            return self._execute_general_llm_fallback(query, reason)
        else:
            return FallbackResult.skip_fallback(reason)

    async def _execute_web_search_fallback(
        self,
        query: str,
        reason: FallbackReason,
        web_search_client: "WebSearchPort | None" = None,
    ) -> FallbackResult:
        """웹 검색 Fallback.

        Args:
            query: 검색어
            reason: Fallback 사유
            web_search_client: 웹 검색 클라이언트 (외부에서 주입)

        Returns:
            FallbackResult: 웹 검색 결과
        """
        if not web_search_client:
            logger.warning("Web search client not available, skipping fallback")
            return FallbackResult.skip_fallback(reason)

        try:
            # 분리수거 키워드 추가
            search_query = f"{query} 분리수거 방법"
            response = await web_search_client.search(
                query=search_query,
                max_results=3,
                region="kr-kr",
            )

            if response.results:
                search_data = {
                    "query": response.query,
                    "results": [
                        {
                            "title": r.title,
                            "url": r.url,
                            "snippet": r.snippet,
                        }
                        for r in response.results
                    ],
                }
                logger.info(f"Web search fallback found {len(response.results)} results")
                return FallbackResult.web_search_fallback(search_data, reason)
            else:
                logger.warning("Web search returned no results")
                return FallbackResult.skip_fallback(reason)

        except Exception as e:
            logger.error(f"Web search fallback failed: {e}")
            return FallbackResult.skip_fallback(reason)

    def _execute_clarification_fallback(
        self,
        query: str,
        state: dict[str, Any],
        reason: FallbackReason,
    ) -> FallbackResult:
        """명확화 요청 Fallback.

        Args:
            query: 사용자 질문
            state: 현재 상태
            reason: Fallback 사유

        Returns:
            FallbackResult: 명확화 요청 결과
        """
        intent = state.get("intent", "general")
        message = CLARIFICATION_MESSAGES.get(intent, CLARIFICATION_MESSAGES["general"])

        logger.info(f"Requesting clarification for intent={intent}")
        return FallbackResult.clarification_fallback(message, reason)

    async def _execute_retry_fallback(
        self,
        state: dict[str, Any],
        reason: FallbackReason,
    ) -> FallbackResult:
        """재시도 Fallback.

        Args:
            state: 현재 상태
            reason: Fallback 사유

        Returns:
            FallbackResult: 재시도 결과
        """
        retry_count = state.get("retry_count", 0)

        if retry_count >= self._max_retries:
            logger.warning(f"Max retries ({self._max_retries}) reached, skipping")
            return FallbackResult.skip_fallback(reason)

        # 재시도는 상위 레이어에서 처리하도록 메타데이터 전달
        return FallbackResult(
            success=False,
            strategy_used="retry",
            reason=reason,
            metadata={"retry_count": retry_count + 1, "should_retry": True},
        )

    def _execute_general_llm_fallback(
        self,
        query: str,
        reason: FallbackReason,
    ) -> FallbackResult:
        """일반 LLM Fallback.

        RAG/웹 검색 모두 실패 시 LLM 지식 기반 답변 생성.

        Args:
            query: 사용자 질문
            reason: Fallback 사유

        Returns:
            FallbackResult: 일반 LLM 결과
        """
        logger.info("Using general LLM fallback")
        return FallbackResult(
            success=True,
            strategy_used="general_llm",
            reason=reason,
            next_node="answer",
            message="정확한 분리수거 정보를 찾지 못했지만, 제가 아는 내용으로 도와드릴게요! 📚",
            metadata={"use_llm_knowledge": True},
        )

    def _get_next_strategy(
        self,
        reason: FallbackReason,
        current_strategy: str | None = None,
    ) -> str:
        """다음 Fallback 전략 결정.

        Args:
            reason: Fallback 사유
            current_strategy: 현재 전략

        Returns:
            다음 전략
        """
        # 사유별 기본 전략
        base_strategy = reason.get_fallback_strategy()

        if current_strategy is None:
            return base_strategy

        # 현재 전략의 다음 전략 찾기
        chain_key = self._get_chain_key(reason)
        chain = FALLBACK_CHAIN.get(chain_key, ["skip"])

        try:
            current_index = chain.index(current_strategy)
            if current_index + 1 < len(chain):
                return chain[current_index + 1]
        except ValueError:
            pass

        return "skip"

    def _get_chain_key(self, reason: FallbackReason) -> str:
        """Fallback 사유에서 체인 키 추출."""
        if reason in (FallbackReason.RAG_NO_RESULT, FallbackReason.RAG_LOW_QUALITY):
            return "rag"
        elif reason == FallbackReason.INTENT_LOW_CONFIDENCE:
            return "intent"
        elif reason == FallbackReason.SUBAGENT_FAILURE:
            return "character"  # 또는 location
        return "rag"

    def should_fallback(
        self,
        state: dict[str, Any],
        feedback: "FeedbackResultType | None" = None,
    ) -> tuple[bool, FallbackReason | None]:
        """Fallback 필요 여부 판단.

        Args:
            state: 현재 상태
            feedback: 품질 평가 결과 (선택)

        Returns:
            (Fallback 필요 여부, 사유)
        """
        # 1. 피드백 기반 판단
        if feedback and feedback.needs_fallback:
            return True, feedback.fallback_reason

        # 2. RAG 결과 없음
        if state.get("intent") == "waste" and not state.get("disposal_rules"):
            return True, FallbackReason.RAG_NO_RESULT

        # 3. Intent 신뢰도 낮음
        confidence = state.get("intent_confidence", 1.0)
        if confidence < 0.3:
            return True, FallbackReason.INTENT_LOW_CONFIDENCE

        # 4. Subagent 실패
        if state.get("subagent_error"):
            return True, FallbackReason.SUBAGENT_FAILURE

        return False, None
