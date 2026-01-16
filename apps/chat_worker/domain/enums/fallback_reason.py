"""Fallback 사유 정의.

자동 재프롬프트가 필요한 사유 분류.
"""

from enum import Enum


class FallbackReason(str, Enum):
    """Fallback 사유 Enum.

    RAG_NO_RESULT: RAG 검색 결과 없음
    RAG_LOW_QUALITY: RAG 결과 품질 낮음
    INTENT_LOW_CONFIDENCE: Intent 신뢰도 낮음
    SUBAGENT_FAILURE: Subagent 호출 실패
    LLM_ERROR: LLM 응답 오류
    USER_CLARIFICATION: 사용자 명확화 필요
    TIMEOUT: 타임아웃
    """

    RAG_NO_RESULT = "rag_no_result"
    RAG_LOW_QUALITY = "rag_low_quality"
    INTENT_LOW_CONFIDENCE = "intent_low_confidence"
    SUBAGENT_FAILURE = "subagent_failure"
    LLM_ERROR = "llm_error"
    USER_CLARIFICATION = "user_clarification"
    TIMEOUT = "timeout"

    def get_fallback_strategy(self) -> str:
        """해당 사유에 대한 Fallback 전략 반환."""
        strategies = {
            FallbackReason.RAG_NO_RESULT: "web_search",
            FallbackReason.RAG_LOW_QUALITY: "web_search",
            FallbackReason.INTENT_LOW_CONFIDENCE: "clarify",
            FallbackReason.SUBAGENT_FAILURE: "retry",
            FallbackReason.LLM_ERROR: "retry",
            FallbackReason.USER_CLARIFICATION: "clarify",
            FallbackReason.TIMEOUT: "retry",
        }
        return strategies.get(self, "skip")

    def is_retryable(self) -> bool:
        """재시도 가능한 사유인지 여부."""
        return self in (
            FallbackReason.SUBAGENT_FAILURE,
            FallbackReason.LLM_ERROR,
            FallbackReason.TIMEOUT,
        )
