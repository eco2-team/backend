"""Answer Generation Node - LangGraph 어댑터.

얇은 어댑터: state 변환 + Command 호출 + progress notify (UX).
정책/흐름은 GenerateAnswerCommand(Application)에서 처리.

Clean Architecture:
- Node(Adapter): 이 파일 - LangGraph glue code
- Command(UseCase): GenerateAnswerCommand - 정책/흐름
- Service: AnswerGeneratorService - 순수 비즈니스 로직
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from chat_worker.application.commands.generate_answer_command import (
    GenerateAnswerCommand,
    GenerateAnswerInput,
)
from chat_worker.infrastructure.assets.prompt_loader import PromptBuilder

if TYPE_CHECKING:
    from chat_worker.application.ports.cache import CachePort
    from chat_worker.application.ports.events import ProgressNotifierPort
    from chat_worker.application.ports.llm import LLMClientPort

logger = logging.getLogger(__name__)


def create_answer_node(
    llm: "LLMClientPort",
    event_publisher: "ProgressNotifierPort",
    cache: "CachePort | None" = None,
):
    """답변 생성 노드 팩토리.

    Node는 LangGraph 어댑터:
    - state → input DTO 변환
    - Command(UseCase) 호출
    - 토큰 스트리밍 → SSE 발행
    - output → state 변환

    Args:
        llm: LLM 클라이언트
        event_publisher: 이벤트 발행자 (SSE)
        cache: 캐시 클라이언트 (선택, Answer 캐싱용)

    Returns:
        answer_node 함수
    """
    # Command(UseCase) 인스턴스 생성 - Port 조립
    prompt_builder = PromptBuilder()
    command = GenerateAnswerCommand(
        llm=llm,
        prompt_builder=prompt_builder,
        cache=cache,
    )

    async def answer_node(state: dict[str, Any]) -> dict[str, Any]:
        """LangGraph 노드 (얇은 어댑터).

        역할:
        1. state에서 값 추출 (LangGraph glue)
        2. Command 호출 (정책/흐름 위임)
        3. 토큰 스트리밍 → SSE (UX)
        4. output → state 변환

        Args:
            state: 현재 LangGraph 상태

        Returns:
            업데이트된 상태
        """
        job_id = state["job_id"]

        # Progress: 시작 (UX)
        await event_publisher.notify_stage(
            task_id=job_id,
            stage="answer",
            status="started",
            progress=70,
            message="💭 답변 고민 중...",
        )

        try:
            # 1. state → input DTO 변환
            # recyclable_price_context에서 context 문자열 추출
            price_ctx = state.get("recyclable_price_context")
            price_context_str = price_ctx.get("context") if isinstance(price_ctx, dict) else None

            # bulk_waste_context에서 context 문자열 추출
            waste_ctx = state.get("bulk_waste_context")
            waste_context_str = waste_ctx.get("context") if isinstance(waste_ctx, dict) else None

            # weather_context에서 context 문자열 추출
            weather_ctx = state.get("weather_context")
            weather_context_str = weather_ctx.get("context") if isinstance(weather_ctx, dict) else None

            # collection_point_context에서 context 문자열 추출
            collection_ctx = state.get("collection_point_context")
            collection_context_str = collection_ctx.get("context") if isinstance(collection_ctx, dict) else None

            input_dto = GenerateAnswerInput(
                job_id=job_id,
                message=state.get("message", ""),
                intent=state.get("intent", "general"),
                additional_intents=state.get("additional_intents", []),
                has_multi_intent=state.get("has_multi_intent", False),
                classification=state.get("classification_result"),
                disposal_rules=state.get("disposal_rules"),
                character_context=state.get("character_context"),
                location_context=state.get("location_context"),
                web_search_results=state.get("web_search_results"),
                recyclable_price_context=price_context_str,
                bulk_waste_context=waste_context_str,
                weather_context=weather_context_str,
                collection_point_context=collection_context_str,
            )

            # 2. Command 실행 (스트리밍)
            answer_parts = []
            async for token in command.execute(input_dto):
                # 토큰 이벤트 발행 (SSE 스트리밍)
                await event_publisher.notify_token(
                    task_id=job_id,
                    content=token,
                )
                answer_parts.append(token)

            answer = "".join(answer_parts)

            logger.info(
                "Answer generated",
                extra={"job_id": job_id, "length": len(answer)},
            )

            # Progress: 완료 (UX)
            await event_publisher.notify_stage(
                task_id=job_id,
                stage="answer",
                status="completed",
                progress=100,
            )

            # 3. output → state 변환
            return {**state, "answer": answer}

        except Exception as e:
            logger.error(
                "Answer generation failed",
                extra={"job_id": job_id, "error": str(e)},
            )
            await event_publisher.notify_stage(
                task_id=job_id,
                stage="answer",
                status="failed",
                result={"error": str(e)},
            )
            return {
                **state,
                "answer": "죄송해요, 답변 생성 중 오류가 발생했어요. 다시 시도해주세요! 🙏",
            }

    return answer_node
