"""Intent Classification Node - 오케스트레이션 전용.

노드 책임: 이벤트 발행 + 서비스 호출 + state 업데이트
비즈니스 로직: IntentClassifier 서비스에 위임

Clean Architecture:
- Node: 오케스트레이션 (이 파일)
- Service: IntentClassifier (비즈니스 로직)
- Domain: Intent, ChatIntent (결과 VO)
- Port: LLMPort (순수 LLM 호출)

P0-P3 개선사항:
- P0: 프롬프트 파일 기반 로딩
- P1: 신뢰도 기반 Fallback
- P2: Intent 캐싱 (Redis 주입)
- P3: 대화 맥락 활용 (context 전달)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from chat_worker.application.intent.services import IntentClassifier

if TYPE_CHECKING:
    from redis.asyncio import Redis

    from chat_worker.application.ports.events import ProgressNotifierPort
    from chat_worker.application.ports.llm import LLMClientPort

logger = logging.getLogger(__name__)


def create_intent_node(
    llm: "LLMClientPort",
    event_publisher: "ProgressNotifierPort",
    redis: "Redis | None" = None,
):
    """의도 분류 노드 팩토리.

    노드는 thin wrapper로:
    1. 이벤트 발행
    2. IntentClassifier 서비스 호출
    3. state 업데이트

    Args:
        llm: LLM 클라이언트
        event_publisher: 이벤트 발행자
        redis: Redis 클라이언트 (P2: 캐싱용)
    """
    # 서비스 인스턴스 (비즈니스 로직 담당)
    classifier = IntentClassifier(llm, redis=redis, enable_cache=redis is not None)

    async def intent_node(state: dict[str, Any]) -> dict[str, Any]:
        job_id = state["job_id"]
        message = state["message"]

        # 1. 이벤트: 시작
        await event_publisher.notify_stage(
            task_id=job_id,
            stage="intent",
            status="started",
            progress=10,
            message="🧠 의도 파악 중...",
        )

        # 2. 서비스 호출 (비즈니스 로직 위임)
        #    반환: ChatIntent (Domain Value Object)
        #    P3: context 전달 (대화 맥락)
        context = state.get("conversation_history")
        chat_intent = await classifier.classify(message, context=context)

        # P2: Multi-Intent 감지 여부
        has_multi_intent = classifier._has_multi_intent(message)

        logger.info(
            "Intent node completed",
            extra={
                "job_id": job_id,
                "intent": chat_intent.intent.value,
                "complexity": chat_intent.complexity.value,
                "confidence": chat_intent.confidence,
                "has_multi_intent": has_multi_intent,
            },
        )

        # 3. 이벤트: 완료
        await event_publisher.notify_stage(
            task_id=job_id,
            stage="intent",
            status="completed",
            progress=20,
            result={
                "intent": chat_intent.intent.value,
                "complexity": chat_intent.complexity.value,
                "confidence": chat_intent.confidence,
            },
        )

        # 4. state 업데이트 (Domain VO → state 병합)
        return {
            **state,
            "intent": chat_intent.intent.value,
            "is_complex": chat_intent.is_complex,
            "intent_confidence": chat_intent.confidence,
            "has_multi_intent": has_multi_intent,  # P2: Multi-Intent 감지
        }

    return intent_node
