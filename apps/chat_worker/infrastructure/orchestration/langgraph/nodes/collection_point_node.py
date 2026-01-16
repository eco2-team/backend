"""Collection Point Node - LangGraph 어댑터.

얇은 어댑터: state 변환 + Command 호출 + progress notify (UX).
정책/흐름은 SearchCollectionPointCommand(Application)에서 처리.

Clean Architecture:
- Node(Adapter): 이 파일 - LangGraph glue code
- Command(UseCase): SearchCollectionPointCommand - 정책/흐름
- Port: CollectionPointClientPort - HTTP API 호출

사용 시나리오:
1. "폐휴대폰 어디서 버려?" → 근처 수거함 위치 안내
2. "폐건전지 수거함" → 수거함 검색
3. 특정 지역 수거함 검색

Flow:
    Router → collection_point → Answer
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from chat_worker.application.commands.search_collection_point_command import (
    SearchCollectionPointCommand,
    SearchCollectionPointInput,
)
from chat_worker.infrastructure.orchestration.langgraph.nodes.node_executor import (
    NodeExecutor,
)

if TYPE_CHECKING:
    from chat_worker.application.ports.collection_point_client import (
        CollectionPointClientPort,
    )
    from chat_worker.application.ports.events import ProgressNotifierPort

logger = logging.getLogger(__name__)


def create_collection_point_node(
    collection_point_client: "CollectionPointClientPort",
    event_publisher: "ProgressNotifierPort",
):
    """수거함 노드 팩토리.

    Node는 LangGraph 어댑터:
    - state → input DTO 변환
    - Command(UseCase) 호출
    - output → state 변환
    - progress notify (UX)

    Args:
        collection_point_client: 수거함 클라이언트
        event_publisher: 이벤트 발행기

    Returns:
        collection_point_node 함수
    """
    # Command(UseCase) 인스턴스 생성 - Port 조립
    command = SearchCollectionPointCommand(
        collection_point_client=collection_point_client
    )

    async def _collection_point_node_inner(state: dict[str, Any]) -> dict[str, Any]:
        """실제 노드 로직 (NodeExecutor가 래핑).

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
            stage="collection_point",
            status="started",
            progress=45,
            message="🗑️ 수거함 위치를 검색 중...",
        )

        # 1. state → input DTO 변환
        # collection_point_address: 직접 지정된 검색어
        # user_location: 사용자 위치에서 주소 추출
        address_keyword = state.get("collection_point_address")
        name_keyword = state.get("collection_point_name")

        input_dto = SearchCollectionPointInput(
            job_id=job_id,
            address_keyword=address_keyword,
            name_keyword=name_keyword,
            user_location=state.get("user_location"),
            limit=5,
        )

        # 2. Command 실행 (정책/흐름은 Command에서)
        output = await command.execute(input_dto)

        # 3. output → state 변환
        if output.needs_location:
            # 위치 정보 필요 → HITL 트리거
            await event_publisher.notify_needs_input(
                task_id=job_id,
                input_type="location",
                message="🗑️ 수거함 위치를 찾으려면 지역 정보가 필요해요.\n어느 지역(구)에서 찾으시나요?",
                timeout=60,
            )
            await event_publisher.notify_stage(
                task_id=job_id,
                stage="collection_point",
                status="waiting",
                message="지역 정보 대기 중...",
            )
            return {
                **state,
                "collection_point_context": output.collection_point_context,
                "needs_location": True,
            }

        if not output.success:
            await event_publisher.notify_stage(
                task_id=job_id,
                stage="collection_point",
                status="failed",
                result={"error": output.error_message},
            )
            return {
                **state,
                "collection_point_context": output.collection_point_context,
                "collection_point_error": output.error_message,
            }

        # Progress: 완료 (UX)
        context = output.collection_point_context or {}
        found = context.get("found", False)
        count = context.get("count", 0)

        result_message = "수거함 정보를 준비했어요!"
        if found:
            result_message = f"✅ {count}곳의 수거함을 찾았어요!"
        elif context.get("type") == "guide":
            result_message = "지역을 알려주세요!"

        await event_publisher.notify_stage(
            task_id=job_id,
            stage="collection_point",
            status="completed",
            progress=55,
            result={
                "found": found,
                "count": count,
            },
            message=result_message,
        )

        return {
            **state,
            "collection_point_context": output.collection_point_context,
        }

    # NodeExecutor로 래핑 (Policy 적용: timeout, retry, circuit breaker)
    executor = NodeExecutor.get_instance()

    async def collection_point_node(state: dict[str, Any]) -> dict[str, Any]:
        """LangGraph 노드 (Policy 적용됨).

        NodeExecutor가 다음을 처리:
        - Circuit Breaker 확인
        - Timeout 적용 (10000ms)
        - Retry (2회)
        - FAIL_FALLBACK 처리 (실패 시 대체 안내)
        """
        return await executor.execute(
            node_name="collection_point",
            node_func=_collection_point_node_inner,
            state=state,
        )

    return collection_point_node


__all__ = ["create_collection_point_node"]
