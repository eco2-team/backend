"""Kakao Place Node - LangGraph 어댑터.

얇은 어댑터: state 변환 + Command 호출 + progress notify (UX).
정책/흐름은 SearchKakaoPlaceCommand(Application)에서 처리.

Clean Architecture:
- Node(Adapter): 이 파일 - LangGraph glue code
- Command(UseCase): SearchKakaoPlaceCommand - 정책/흐름
- Service: KakaoPlaceService - 순수 비즈니스 로직

Function Calling:
- LLM이 사용자 메시지에서 검색 파라미터를 동적으로 추출
- 검색어, 반경, 카테고리 등을 자동 파싱
- Heuristic 대신 LLM 기반 파라미터 결정

사용 시나리오:
1. 주변 재활용센터 검색
2. 제로웨이스트샵 검색
3. 일반 장소 검색

Flow:
    Router → kakao_place (Function Calling) → API 실행 → Answer
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from chat_worker.application.commands.search_kakao_place_command import (
    SearchKakaoPlaceCommand,
    SearchKakaoPlaceInput,
)
from chat_worker.infrastructure.orchestration.langgraph.context_helper import (
    create_error_context,
)

if TYPE_CHECKING:
    from chat_worker.application.ports.events import ProgressNotifierPort
    from chat_worker.application.ports.kakao_local_client import KakaoLocalClientPort
    from chat_worker.application.ports.llm import LLMClientPort

logger = logging.getLogger(__name__)

# Function Definition for OpenAI Function Calling
KAKAO_PLACE_FUNCTION = {
    "name": "search_kakao_place",
    "description": "카카오맵 API로 장소를 검색합니다. 재활용센터, 제로웨이스트샵, 일반 장소 검색에 사용됩니다.",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "검색할 키워드 (예: '재활용센터', '제로웨이스트샵', '카페')",
            },
            "search_type": {
                "type": "string",
                "enum": ["keyword", "category"],
                "description": "검색 타입. keyword=키워드 검색, category=카테고리 검색",
            },
            "category_code": {
                "type": "string",
                "description": "카테고리 코드 (search_type=category일 때). 예: CE7 (카페)",
            },
            "radius": {
                "type": "integer",
                "description": "검색 반경(미터). 기본값 5000m",
                "default": 5000,
            },
        },
        "required": ["query", "search_type"],
    },
}


def create_kakao_place_node(
    kakao_client: "KakaoLocalClientPort",
    event_publisher: "ProgressNotifierPort",
    llm: "LLMClientPort",
):
    """카카오 장소 검색 노드 팩토리.

    Node는 LangGraph 어댑터:
    - state → input DTO 변환
    - LLM Function Calling으로 파라미터 추출
    - Command(UseCase) 호출
    - output → state 변환
    - progress notify (UX)

    Args:
        kakao_client: 카카오 로컬 클라이언트
        event_publisher: 이벤트 발행기
        llm: LLM 클라이언트 (Function Calling용)

    Returns:
        kakao_place_node 함수
    """
    # Command(UseCase) 인스턴스 생성 - Port 조립
    command = SearchKakaoPlaceCommand(kakao_client=kakao_client)

    async def kakao_place_node(state: dict[str, Any]) -> dict[str, Any]:
        """LangGraph 노드 (얇은 어댑터).

        역할:
        1. state에서 값 추출 (LangGraph glue)
        2. LLM Function Calling으로 파라미터 추출
        3. Command 호출 (정책/흐름 위임)
        4. output → state 변환
        5. progress notify (UX)

        Args:
            state: 현재 LangGraph 상태

        Returns:
            업데이트된 상태
        """
        job_id = state.get("job_id", "")
        message = state.get("message", "")

        # Progress: 시작 (UX)
        await event_publisher.notify_stage(
            task_id=job_id,
            stage="kakao_place",
            status="started",
            progress=45,
            message="주변 장소 검색 중",
        )

        # 1. LLM Function Calling으로 파라미터 추출
        system_prompt = """사용자의 메시지에서 장소 검색에 필요한 정보를 추출하세요.

지침:
- 재활용센터, 수거함, 제로웨이스트샵 등의 키워드 파악
- 검색 타입은 대부분 "keyword" 사용
- 반경은 명시되지 않으면 5000m 사용
- 사용자가 "주변", "근처" 등의 키워드를 사용하면 주변 검색 의도입니다.

예시:
- "주변 재활용센터 찾아줘" → query: "재활용센터", search_type: "keyword", radius: 5000
- "3km 이내 제로웨이스트샵" → query: "제로웨이스트샵", search_type: "keyword", radius: 3000
- "근처 카페" → query: "카페", search_type: "keyword", radius: 5000
"""

        try:
            func_name, func_args = await llm.generate_function_call(
                prompt=message,
                functions=[KAKAO_PLACE_FUNCTION],
                system_prompt=system_prompt,
                function_call={"name": "search_kakao_place"},  # 강제 호출
            )

            if not func_args:
                # Function call 실패 → fallback: 메시지를 query로 사용
                logger.warning(
                    "Function call failed, using fallback",
                    extra={"job_id": job_id, "user_message": message},
                )
                func_args = {
                    "query": message,
                    "search_type": "keyword",
                    "radius": 5000,
                }

        except Exception as e:
            # LLM 호출 실패 → fallback
            logger.error(
                f"Function calling error: {e}",
                extra={"job_id": job_id, "user_message": message},
            )
            await event_publisher.notify_stage(
                task_id=job_id,
                stage="kakao_place",
                status="failed",
                result={"error": "파라미터 추출 실패"},
            )
            return {
                "location_context": create_error_context(
                    producer="location",
                    job_id=job_id,
                    error=f"검색 정보를 추출할 수 없습니다: {str(e)}",
                ),
            }

        # 2. Function call 결과 → input DTO 변환
        input_dto = SearchKakaoPlaceInput(
            job_id=job_id,
            query=func_args.get("query", message),
            search_type=func_args.get("search_type", "keyword"),
            category_code=func_args.get("category_code"),
            radius=func_args.get("radius", 5000),
            user_location=state.get("user_location"),
            limit=10,
        )

        # 3. Command 실행 (정책/흐름은 Command에서)
        output = await command.execute(input_dto)

        # 4. output → state 변환
        if output.needs_location:
            # 위치 정보 필요 → HITL 트리거
            await event_publisher.notify_needs_input(
                task_id=job_id,
                input_type="location",
                message="주변 장소를 찾으려면 위치 정보가 필요합니다. 위치 권한을 허용해주세요.",
                timeout=60,
            )
            await event_publisher.notify_stage(
                task_id=job_id,
                stage="kakao_place",
                status="waiting",
                message="위치 정보 대기 중...",
            )
            return {
                **state,
                "location_context": output.places_context,
                "needs_location": True,
            }

        if not output.success:
            await event_publisher.notify_stage(
                task_id=job_id,
                stage="kakao_place",
                status="failed",
                result={"error": output.error_message},
            )
            return {
                **state,
                "location_context": output.places_context,
                "location_error": output.error_message,
            }

        # Progress: 완료 (UX)
        found = output.places_context.get("found", False) if output.places_context else False
        count = output.places_context.get("count", 0) if output.places_context else 0

        await event_publisher.notify_stage(
            task_id=job_id,
            stage="kakao_place",
            status="completed",
            progress=55,
            result={
                "found": found,
                "count": count,
            },
            message=f"{count}개 장소 검색 완료" if found else "검색 결과 없음",
        )

        return {
            **state,
            "location_context": output.places_context,
        }

    return kakao_place_node


__all__ = ["create_kakao_place_node"]
