"""Intent Classification Node - 오케스트레이션 전용.

노드 책임: 이벤트 발행 + 서비스 호출 + state 업데이트
비즈니스 로직: IntentClassifier 서비스에 위임

Clean Architecture:
- Node: 오케스트레이션 (이 파일)
- Service: IntentClassifier (비즈니스 로직)
- Domain: Intent, ChatIntent (결과 VO)
- Port: LLMPort (순수 LLM 호출)

면접 포인트 (C):
Q: "LangGraph 노드에 로직이 많으면 infrastructure가 application을 먹지 않나요?"
A: "노드는 orchestration만 담당합니다:
    1. 이벤트 발행 (시작)
    2. 서비스 호출 (비즈니스 로직 위임)
    3. state 업데이트
    4. 이벤트 발행 (완료)
    실제 로직은 application/services에 있어서 테스트와 재사용이 용이합니다."
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from chat_worker.application.intent.services import IntentClassifier

if TYPE_CHECKING:
    from chat_worker.application.ports.events import ProgressNotifierPort
    from chat_worker.application.ports.llm import LLMClientPort

logger = logging.getLogger(__name__)


def create_intent_node(
    llm: "LLMClientPort",
    event_publisher: "ProgressNotifierPort",
):
    """의도 분류 노드 팩토리.

    노드는 thin wrapper로:
    1. 이벤트 발행
    2. IntentClassifier 서비스 호출
    3. state 업데이트
    """
    # 서비스 인스턴스 (비즈니스 로직 담당)
    classifier = IntentClassifier(llm)

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
        chat_intent = await classifier.classify(message)

        logger.info(
            "Intent node completed",
            extra={
                "job_id": job_id,
                "intent": chat_intent.intent.value,
                "complexity": chat_intent.complexity.value,
                "confidence": chat_intent.confidence,
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
            },
        )

        # 4. state 업데이트 (Domain VO → state 병합)
        return {
            **state,
            "intent": chat_intent.intent.value,
            "is_complex": chat_intent.is_complex,
        }

    return intent_node
