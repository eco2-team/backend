"""Character Subagent Node - 오케스트레이션 전용.

LangGraph 파이프라인의 캐릭터 정보 조회 노드입니다.

노드 책임: 이벤트 발행 + 서비스 호출 + state 업데이트
비즈니스 로직: CharacterService에 위임

흐름:
1. 사용자 메시지에서 폐기물 카테고리 추출 (LLM)
2. CharacterService로 캐릭터 조회
3. 컨텍스트에 캐릭터 정보 추가

왜 동기(gRPC)인가?
- LangGraph는 asyncio 기반
- gRPC는 grpc.aio로 asyncio 네이티브 지원
- Character API의 LocalCache는 즉시 응답 (~1-3ms)
- Celery는 Fire & Forget에 적합, 결과 대기에 부적합

Clean Architecture:
- Node: 오케스트레이션 (이 파일)
- Service: CharacterService (비즈니스 로직)
- Port: CharacterClientPort (API 호출)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from chat_worker.application.integrations.character.services import CharacterService

if TYPE_CHECKING:
    from chat_worker.application.integrations.character.ports import CharacterClientPort
    from chat_worker.application.ports.events import ProgressNotifierPort
    from chat_worker.application.ports.llm import LLMClientPort

logger = logging.getLogger(__name__)

# LLM에게 폐기물 카테고리를 추출하도록 하는 프롬프트
EXTRACT_CATEGORY_PROMPT = """사용자 질문에서 폐기물 중분류를 추출해주세요.

가능한 카테고리:
- 플라스틱
- 종이류
- 캔류
- 유리류
- 비닐류
- 스티로폼
- 음식물쓰레기
- 소형가전
- 의류
- 일반쓰레기

사용자 질문: {message}

응답 형식: 카테고리명만 (예: "플라스틱")
추출할 수 없으면 "unknown" 반환
"""


def create_character_subagent_node(
    llm: "LLMClientPort",
    character_client: "CharacterClientPort",
    event_publisher: "ProgressNotifierPort",
):
    """Character Subagent 노드 생성.

    노드는 thin wrapper로:
    1. 이벤트 발행
    2. CharacterService 호출
    3. state 업데이트

    Args:
        llm: LLM 클라이언트 (카테고리 추출용)
        character_client: Character gRPC/HTTP 클라이언트
        event_publisher: 이벤트 발행자 (SSE 진행 상황)

    Returns:
        LangGraph 노드 함수
    """
    # 서비스 인스턴스 (비즈니스 로직 담당)
    character_service = CharacterService(character_client)

    async def character_subagent(state: dict[str, Any]) -> dict[str, Any]:
        """캐릭터 정보를 조회합니다.

        1. LLM으로 폐기물 카테고리 추출
        2. CharacterService로 캐릭터 조회
        3. 컨텍스트에 캐릭터 정보 추가
        """
        job_id = state.get("job_id", "")
        message = state.get("message", "")

        # 1. 이벤트: 시작
        await event_publisher.notify_stage(
            task_id=job_id,
            stage="character",
            status="processing",
            progress=50,
            message="🎭 캐릭터 정보를 찾고 있어요...",
        )

        # 2. 폐기물 카테고리 추출 (LLM)
        try:
            prompt = EXTRACT_CATEGORY_PROMPT.format(message=message)
            waste_category = await llm.generate(
                prompt=prompt,
                system_prompt="당신은 폐기물 분류 전문가입니다. 질문에서 폐기물 카테고리만 추출하세요.",
                max_tokens=20,
                temperature=0.1,
            )
            waste_category = waste_category.strip().strip('"').strip("'")

            if waste_category.lower() == "unknown" or not waste_category:
                logger.info(
                    "Could not extract waste category",
                    extra={"job_id": job_id, "message": message},
                )
                return {
                    **state,
                    "character_context": None,
                    "subagent_error": "폐기물 종류를 파악하지 못했어요. 좀 더 구체적으로 물어봐주세요!",
                }

        except Exception as e:
            logger.error(
                "Failed to extract waste category",
                extra={"job_id": job_id, "error": str(e)},
            )
            return {
                **state,
                "character_context": None,
                "subagent_error": "죄송해요, 질문을 이해하지 못했어요.",
            }

        # 3. CharacterService로 캐릭터 조회
        try:
            character = await character_service.find_by_waste_category(waste_category)

            if character is None:
                logger.info(
                    "Character not found for category",
                    extra={
                        "job_id": job_id,
                        "waste_category": waste_category,
                    },
                )
                return {
                    **state,
                    "character_context": {
                        "waste_category": waste_category,
                        "found": False,
                    },
                }

            # 4. 컨텍스트 구성 (Service의 메서드 사용)
            logger.info(
                "Character found",
                extra={
                    "job_id": job_id,
                    "waste_category": waste_category,
                    "character_name": character.name,
                },
            )

            # CharacterService.to_answer_context() 사용
            char_context = CharacterService.to_answer_context(character)
            char_context["waste_category"] = waste_category
            char_context["found"] = True

            return {
                **state,
                "character_context": char_context,
            }

        except Exception as e:
            logger.error(
                "Character service call failed",
                extra={"job_id": job_id, "error": str(e)},
            )
            return {
                **state,
                "character_context": None,
                "subagent_error": "캐릭터 정보를 가져오는 데 실패했어요.",
            }

    return character_subagent
