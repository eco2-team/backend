"""Answer Generation Node - 오케스트레이션 전용.

노드 책임: 이벤트 발행 + 서비스 호출 + state 업데이트
비즈니스 로직: AnswerGeneratorService에 위임

Clean Architecture:
- Node: 오케스트레이션 (이 파일)
- Service: AnswerGeneratorService (비즈니스 로직)
- Port: LLMPort (순수 LLM 호출)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from chat_worker.application.answer.dto import AnswerContext
from chat_worker.application.answer.services import AnswerGeneratorService

if TYPE_CHECKING:
    from chat_worker.application.ports.events import ProgressNotifierPort
    from chat_worker.application.ports.llm import LLMClientPort

logger = logging.getLogger(__name__)

ANSWER_SYSTEM_PROMPT = """너는 "이코"야, Eco² 앱의 친절한 분리배출 도우미.

## 성격
- 친절하고 귀여운 말투
- 환경 보호에 열정적

## 답변 규칙
1. 간결하고 실용적인 정보 제공
2. 분리배출 방법은 단계별로 설명
3. 잘못된 정보보다 모른다고 솔직히 말하기
4. 사용자를 격려하고 응원하기
"""


def create_answer_node(
    llm: "LLMClientPort",
    event_publisher: "ProgressNotifierPort",
):
    """답변 생성 노드 팩토리.

    노드는 thin wrapper로:
    1. 이벤트 발행
    2. AnswerGeneratorService 호출
    3. state 업데이트
    """
    # 서비스 인스턴스 (비즈니스 로직 담당)
    answer_service = AnswerGeneratorService(llm)

    async def answer_node(state: dict[str, Any]) -> dict[str, Any]:
        job_id = state["job_id"]
        message = state.get("message", "")
        classification = state.get("classification_result")
        disposal_rules = state.get("disposal_rules")
        character_context = state.get("character_context")
        location_context = state.get("location_context")

        # 1. 이벤트: 시작
        await event_publisher.notify_stage(
            task_id=job_id,
            stage="answer",
            status="started",
            progress=70,
            message="💭 답변 고민 중...",
        )

        try:
            # 2. 컨텍스트 구성 (Service의 팩토리 메서드 사용)
            context = AnswerContext(
                classification=classification,
                disposal_rules=disposal_rules.get("data") if disposal_rules else None,
                character_context=character_context,
                location_context=location_context,
                user_input=message,
            )

            # 3. 서비스 호출 (스트리밍)
            answer_parts = []
            async for token in answer_service.generate_stream(
                context=context,
                system_prompt=ANSWER_SYSTEM_PROMPT,
            ):
                # 토큰 이벤트 발행 (SSE 스트리밍)
                await event_publisher.notify_token(
                    task_id=job_id,
                    content=token,
                )
                answer_parts.append(token)

            answer = "".join(answer_parts)

            logger.info(
                "Answer generated",
                extra={
                    "job_id": job_id,
                    "length": len(answer),
                },
            )

            # 4. 이벤트: 완료
            await event_publisher.notify_stage(
                task_id=job_id,
                stage="answer",
                status="completed",
                progress=100,
            )

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
