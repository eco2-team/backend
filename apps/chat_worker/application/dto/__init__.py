"""Application DTOs (Layer-first).

모든 Data Transfer Object를 한 곳에서 관리.
Command Input/Output 및 Service 간 데이터 전달용.

Layer-first 구조:
- dto/: 이 폴더 (데이터 전송 객체)
- services/: 비즈니스 로직
- commands/: UseCase (정책/흐름)
- ports/: 추상화 (인터페이스)

카테고리:
- Intent: ChatIntent (domain에서 import), IntentResult, IntentSignals
- Answer: AnswerContext, AnswerResult
- Feedback: FeedbackResult
- Fallback: FallbackResult
- Node: NodeResult, NodeStatus (Production Architecture)
"""

# Answer Context & Result
from chat_worker.application.dto.answer_context import AnswerContext, AnswerResult

# Fallback Result
from chat_worker.application.dto.fallback_result import FallbackResult

# Feedback Result
from chat_worker.application.dto.feedback_result import FeedbackResult

# Intent Result & Signals
from chat_worker.application.dto.intent_result import IntentResult
from chat_worker.application.dto.intent_signals import IntentSignals

# Node Result (Production Architecture)
from chat_worker.application.dto.node_result import NodeResult, NodeStatus

# Intent (Domain Value Object)
from chat_worker.domain import ChatIntent

__all__ = [
    # Intent
    "ChatIntent",
    "IntentResult",
    "IntentSignals",
    # Answer
    "AnswerContext",
    "AnswerResult",
    # Feedback
    "FeedbackResult",
    # Fallback
    "FallbackResult",
    # Node (Production Architecture)
    "NodeResult",
    "NodeStatus",
]
