"""Kakao Place Node - LangGraph 어댑터.

얇은 어댑터: state 변환 + Command 호출 + progress notify (UX).
정책/흐름은 SearchKakaoPlaceCommand(Application)에서 처리.

Clean Architecture:
- Node(Adapter): 이 파일 - LangGraph glue code
- Command(UseCase): SearchKakaoPlaceCommand - 정책/흐름
- Service: KakaoPlaceService - 순수 비즈니스 로직

사용 시나리오:
1. 주변 재활용센터 검색
2. 제로웨이스트샵 검색
3. 일반 장소 검색

Flow:
    Router → kakao_place → Answer
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from chat_worker.application.commands.search_kakao_place_command import (
    SearchKakaoPlaceCommand,
    SearchKakaoPlaceInput,
)

if TYPE_CHECKING:
    from chat_worker.application.ports.events import ProgressNotifierPort
    from chat_worker.application.ports.kakao_local_client import KakaoLocalClientPort

logger = logging.getLogger(__name__)


def create_kakao_place_node(
    kakao_client: "KakaoLocalClientPort",
    event_publisher: "ProgressNotifierPort",
):
    """카카오 장소 검색 노드 팩토리.

    Node는 LangGraph 어댑터:
    - state → input DTO 변환
    - Command(UseCase) 호출
    - output → state 변환
    - progress notify (UX)

    Args:
        kakao_client: 카카오 로컬 클라이언트
        event_publisher: 이벤트 발행기

    Returns:
        kakao_place_node 함수
    """
    # Command(UseCase) 인스턴스 생성 - Port 조립
    command = SearchKakaoPlaceCommand(kakao_client=kakao_client)

    async def kakao_place_node(state: dict[str, Any]) -> dict[str, Any]:
        """LangGraph 노드 (얇은 어댑터).

        역할:
        1. state에서 값 추출 (LangGraph glue)
        2. Command 호출 (정책/흐름 위임)
        3. output → state 변환
        4. progress notify (UX)

        Args:
            state: 현재 LangGraph 상태

        Returns:
            업데이트된 상태
        """
        job_id = state.get("job_id", "")

        # Progress: 시작 (UX)
        await event_publisher.notify_stage(
            task_id=job_id,
            stage="kakao_place",
            status="started",
            progress=45,
            message="주변 장소 검색 중",
        )

        # 1. state → input DTO 변환
        # 검색어: place_query 우선, 없으면 message 사용
        query = state.get("place_query") or state.get("message", "")

        # 검색 타입: 명시된 값 또는 기본 keyword
        search_type = state.get("kakao_search_type", "keyword")

        input_dto = SearchKakaoPlaceInput(
            job_id=job_id,
            query=query,
            user_location=state.get("user_location"),
            search_type=search_type,
            category_code=state.get("kakao_category_code"),
            radius=state.get("search_radius", 5000),
            limit=10,
        )

        # 2. Command 실행 (정책/흐름은 Command에서)
        output = await command.execute(input_dto)

        # 3. output → state 변환
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
                "kakao_place_context": output.places_context,
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
                "kakao_place_context": output.places_context,
                "kakao_place_error": output.error_message,
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
            "kakao_place_context": output.places_context,
        }

    return kakao_place_node


__all__ = ["create_kakao_place_node"]
