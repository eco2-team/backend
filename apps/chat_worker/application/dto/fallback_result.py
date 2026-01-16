"""Fallback Result DTO.

Fallback 실행 결과를 담는 Data Transfer Object.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from chat_worker.domain.enums import FallbackReason


@dataclass
class FallbackResult:
    """Fallback 실행 결과.

    Attributes:
        success: 성공 여부
        strategy_used: 사용된 전략
        reason: Fallback 사유
        data: Fallback으로 얻은 데이터
        next_node: 다음 라우팅 노드
        message: 사용자 메시지 (clarification 등)
        metadata: 추가 메타데이터
    """

    success: bool
    strategy_used: str
    reason: FallbackReason
    data: dict[str, Any] = field(default_factory=dict)
    next_node: str | None = None
    message: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def web_search_fallback(
        cls,
        search_results: dict[str, Any],
        reason: FallbackReason = FallbackReason.RAG_NO_RESULT,
    ) -> "FallbackResult":
        """웹 검색 Fallback 결과."""
        return cls(
            success=bool(search_results),
            strategy_used="web_search",
            reason=reason,
            data={"web_search_results": search_results},
            next_node="answer",
        )

    @classmethod
    def clarification_fallback(
        cls,
        clarification_message: str,
        reason: FallbackReason = FallbackReason.INTENT_LOW_CONFIDENCE,
    ) -> "FallbackResult":
        """명확화 요청 Fallback 결과."""
        return cls(
            success=True,
            strategy_used="clarify",
            reason=reason,
            message=clarification_message,
            next_node="answer",  # 명확화 메시지를 답변으로 전달
        )

    @classmethod
    def retry_success(
        cls,
        retry_data: dict[str, Any],
        reason: FallbackReason,
    ) -> "FallbackResult":
        """재시도 성공 결과."""
        return cls(
            success=True,
            strategy_used="retry",
            reason=reason,
            data=retry_data,
            next_node="answer",
        )

    @classmethod
    def skip_fallback(
        cls,
        reason: FallbackReason,
    ) -> "FallbackResult":
        """Fallback 스킵 (최종 실패)."""
        return cls(
            success=False,
            strategy_used="skip",
            reason=reason,
            next_node="answer",  # 실패해도 answer로 진행
            message="관련 정보를 찾지 못했어요. 일반적인 답변으로 도와드릴게요.",
        )

    def to_state_update(self) -> dict[str, Any]:
        """LangGraph state 업데이트용 딕셔너리 변환."""
        update = {
            "fallback_used": True,
            "fallback_strategy": self.strategy_used,
            "fallback_success": self.success,
        }

        if self.data:
            update.update(self.data)

        if self.message:
            update["fallback_message"] = self.message

        return update

    def to_dict(self) -> dict[str, Any]:
        """딕셔너리 변환."""
        return {
            "success": self.success,
            "strategy_used": self.strategy_used,
            "reason": self.reason.value,
            "data": self.data,
            "next_node": self.next_node,
            "message": self.message,
            "metadata": self.metadata,
        }
