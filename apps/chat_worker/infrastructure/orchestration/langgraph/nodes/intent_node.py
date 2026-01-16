"""Intent Classification Node - LangGraph 어댑터.

얇은 어댑터: state 변환 + Command 호출 + progress notify (UX).
정책/흐름은 ClassifyIntentCommand(Application)에서 처리.

Clean Architecture:
- Node(Adapter): 이 파일 - LangGraph glue code
- Command(UseCase): ClassifyIntentCommand - 정책/흐름
- Service: IntentClassifier, MultiIntentClassifier - 순수 비즈니스 로직
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from chat_worker.application.commands.classify_intent_command import (
    ClassifyIntentCommand,
    ClassifyIntentInput,
)

if TYPE_CHECKING:
    from chat_worker.application.ports.cache import CachePort
    from chat_worker.application.ports.events import ProgressNotifierPort
    from chat_worker.application.ports.llm import LLMClientPort
    from chat_worker.application.ports.prompt_loader import PromptLoaderPort

logger = logging.getLogger(__name__)


def create_intent_node(
    llm: "LLMClientPort",
    event_publisher: "ProgressNotifierPort",
    prompt_loader: "PromptLoaderPort",
    cache: "CachePort | None" = None,
    enable_multi_intent: bool = True,
):
    """의도 분류 노드 팩토리.

    Node는 LangGraph 어댑터:
    - state → input DTO 변환
    - Command(UseCase) 호출
    - output → state 변환
    - progress notify (UX)

    Args:
        llm: LLM 클라이언트
        event_publisher: 이벤트 발행자
        prompt_loader: 프롬프트 로더
        cache: 캐시 Port
        enable_multi_intent: Multi-Intent 처리 활성화 여부

    Returns:
        intent_node 함수
    """
    # Command(UseCase) 인스턴스 생성 - Port 조립
    command = ClassifyIntentCommand(
        llm=llm,
        prompt_loader=prompt_loader,
        cache=cache,
        enable_multi_intent=enable_multi_intent,
    )

    async def intent_node(state: dict[str, Any]) -> dict[str, Any]:
        """LangGraph 노드 (얇은 어댑터).

        역할:
        1. state에서 값 추출 (LangGraph glue)
        2. Command 호출 (정책/흐름 위임)
        3. output → state 변환

        Args:
            state: 현재 LangGraph 상태

        Returns:
            업데이트된 상태
        """
        job_id = state["job_id"]

        # Progress: 시작 (UX)
        await event_publisher.notify_stage(
            task_id=job_id,
            stage="intent",
            status="started",
            progress=10,
            message="🧠 의도 파악 중...",
        )

        # 1. state → input DTO 변환
        # Chain-of-Intent: 이전 intent 히스토리 추출 (예: ["waste", "location"])
        intent_history: list[str] = state.get("intent_history", [])

        input_dto = ClassifyIntentInput(
            job_id=job_id,
            message=state["message"],
            conversation_history=state.get("conversation_history"),
            previous_intents=intent_history if intent_history else None,
        )

        # 2. Command 실행 (정책/흐름은 Command에서)
        output = await command.execute(input_dto)

        logger.info(
            "Intent node completed",
            extra={
                "job_id": job_id,
                "intent": output.intent,
                "confidence": output.confidence,
                "has_multi_intent": output.has_multi_intent,
            },
        )

        # Progress: 완료 (UX)
        await event_publisher.notify_stage(
            task_id=job_id,
            stage="intent",
            status="completed",
            progress=20,
            result={
                "intent": output.intent,
                "complexity": "complex" if output.is_complex else "simple",
                "confidence": output.confidence,
                "has_multi_intent": output.has_multi_intent,
                "additional_intents": output.additional_intents,
            },
        )

        # 3. output → state 변환
        decomposed_queries = output.decomposed_queries or [state["message"]]

        # Chain-of-Intent: intent_history 누적 (이번 intent 추가)
        updated_intent_history = intent_history + [output.intent]

        return {
            **state,
            "intent": output.intent,
            "is_complex": output.is_complex,
            "intent_confidence": output.confidence,
            "has_multi_intent": output.has_multi_intent,
            "additional_intents": output.additional_intents,
            "decomposed_queries": decomposed_queries,
            "current_query": decomposed_queries[0] if decomposed_queries else state["message"],
            "intent_history": updated_intent_history,  # Chain-of-Intent 히스토리
        }

    return intent_node
