"""Feedback Node - LangGraph 어댑터.

얇은 어댑터: state 변환 + Command 호출 + progress notify (UX).
정책/흐름은 EvaluateFeedbackCommand(Application)에서 처리.

Clean Architecture:
- Node(Adapter): 이 파일 - LangGraph glue code
- Command(UseCase): EvaluateFeedbackCommand - 정책/흐름
- Service: FeedbackEvaluatorService - 순수 비즈니스 로직
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from chat_worker.application.commands.evaluate_feedback_command import (
    EvaluateFeedbackCommand,
    EvaluateFeedbackInput,
)

if TYPE_CHECKING:
    from chat_worker.application.services.fallback_orchestrator import FallbackOrchestrator
    from chat_worker.application.ports.llm_evaluator import LLMFeedbackEvaluatorPort
    from chat_worker.application.ports.events import ProgressNotifierPort
    from chat_worker.application.ports.web_search import WebSearchPort

logger = logging.getLogger(__name__)


def create_feedback_node(
    fallback_orchestrator: "FallbackOrchestrator",
    event_publisher: "ProgressNotifierPort",
    llm_evaluator: "LLMFeedbackEvaluatorPort | None" = None,
    web_search_client: "WebSearchPort | None" = None,
):
    """피드백 노드 팩토리.

    Node는 LangGraph 어댑터:
    - state → input DTO 변환
    - Command(UseCase) 호출
    - output → state 변환
    - progress notify (UX)

    Args:
        fallback_orchestrator: Fallback 오케스트레이터
        event_publisher: 진행률 이벤트 발행자 (UX)
        llm_evaluator: LLM 평가기 (선택)
        web_search_client: 웹 검색 클라이언트 (선택)

    Returns:
        feedback_node 함수
    """
    # Command(UseCase) 인스턴스 생성 - Port 조립
    command = EvaluateFeedbackCommand(
        fallback_orchestrator=fallback_orchestrator,
        llm_evaluator=llm_evaluator,
        web_search_client=web_search_client,
    )

    async def feedback_node(state: dict[str, Any]) -> dict[str, Any]:
        """LangGraph 노드 (얇은 어댑터).

        역할:
        1. state에서 값 추출 (LangGraph glue)
        2. Command 호출 (정책/흐름 위임)
        3. 도메인 이벤트 → progress notify (UX)
        4. output → state 변환

        Args:
            state: 현재 LangGraph 상태

        Returns:
            업데이트된 상태
        """
        job_id = state.get("job_id", "")
        intent = state.get("intent", "general")

        # waste intent가 아니면 스킵 (라우팅 로직)
        if intent != "waste":
            return state

        # Progress: 시작 (UX)
        await event_publisher.notify_stage(
            task_id=job_id,
            stage="feedback",
            status="started",
            progress=55,
            message="결과 품질 확인 중",
        )

        try:
            # 1. state → input DTO 변환
            input_dto = EvaluateFeedbackInput(
                job_id=job_id,
                query=state.get("message", ""),
                intent=intent,
                rag_results=state.get("disposal_rules"),
            )

            # 2. Command 실행 (정책/흐름은 여기서)
            output = await command.execute(input_dto)

            # 3. 도메인 이벤트 → progress notify (UX)
            if "fallback_started" in output.events:
                await event_publisher.notify_stage(
                    task_id=job_id,
                    stage="feedback",
                    status="fallback",
                    progress=57,
                    message="추가 정보 검색 중",
                )

            # 4. output → state 변환
            state_update = {
                **state,
                "rag_feedback": output.feedback.to_dict(),
                "rag_quality_score": output.feedback.score,
            }

            if output.fallback_result:
                state_update.update(output.fallback_result.to_state_update())
                if output.fallback_result.message:
                    state_update["fallback_message"] = output.fallback_result.message

            # Progress: 완료 (UX)
            quality = output.feedback.quality.value
            await event_publisher.notify_stage(
                task_id=job_id,
                stage="feedback",
                status="completed",
                progress=60,
                result={
                    "quality": quality,
                    "fallback_used": output.fallback_executed,
                },
                message=f"품질 확인 완료: {quality}",
            )

            return state_update

        except Exception as e:
            logger.error(f"Feedback node failed: {e}", extra={"job_id": job_id})
            await event_publisher.notify_stage(
                task_id=job_id,
                stage="feedback",
                status="failed",
                result={"error": str(e)},
            )
            return state

    return feedback_node


def route_after_feedback(state: dict[str, Any]) -> str:
    """피드백 후 라우팅.

    Fallback 결과에 따라 다음 노드 결정.

    Args:
        state: 현재 상태

    Returns:
        다음 노드 이름
    """
    # Clarification 필요시 바로 answer로 (명확화 메시지 전달)
    if state.get("fallback_strategy") == "clarify":
        return "answer"

    # HITL 필요시 (향후 확장)
    if state.get("fallback_strategy") == "ask_user":
        return "answer"

    # 기본적으로 answer로
    return "answer"
