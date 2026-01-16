"""Bulk Waste Node - LangGraph 어댑터.

얇은 어댑터: state 변환 + Command 호출 + progress notify (UX).
정책/흐름은 SearchBulkWasteCommand(Application)에서 처리.

Clean Architecture:
- Node(Adapter): 이 파일 - LangGraph glue code
- Command(UseCase): SearchBulkWasteCommand - 정책/흐름
- Service: BulkWasteService - 순수 비즈니스 로직

사용 시나리오:
1. 대형폐기물 수거 신청 방법 안내
2. 대형폐기물 품목별 수수료 조회
3. 지역별 배출 방법 안내

Flow:
    Router → bulk_waste → Answer
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from chat_worker.application.commands.search_bulk_waste_command import (
    SearchBulkWasteCommand,
    SearchBulkWasteInput,
)
from chat_worker.infrastructure.orchestration.langgraph.nodes.node_executor import (
    NodeExecutor,
)

if TYPE_CHECKING:
    from chat_worker.application.ports.bulk_waste_client import BulkWasteClientPort
    from chat_worker.application.ports.events import ProgressNotifierPort

logger = logging.getLogger(__name__)


def create_bulk_waste_node(
    bulk_waste_client: "BulkWasteClientPort",
    event_publisher: "ProgressNotifierPort",
):
    """대형폐기물 노드 팩토리.

    Node는 LangGraph 어댑터:
    - state → input DTO 변환
    - Command(UseCase) 호출
    - output → state 변환
    - progress notify (UX)

    Args:
        bulk_waste_client: 대형폐기물 클라이언트
        event_publisher: 이벤트 발행기

    Returns:
        bulk_waste_node 함수
    """
    # Command(UseCase) 인스턴스 생성 - Port 조립
    command = SearchBulkWasteCommand(bulk_waste_client=bulk_waste_client)

    async def _bulk_waste_node_inner(state: dict[str, Any]) -> dict[str, Any]:
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
            stage="bulk_waste",
            status="started",
            progress=45,
            message="🗑️ 대형폐기물 정보를 조회 중...",
        )

        # 1. state → input DTO 변환
        # 시군구: bulk_waste_sigungu 우선, 없으면 user_location에서 추출
        sigungu = state.get("bulk_waste_sigungu")

        # 품목명: bulk_waste_item 필드 (수수료 조회용)
        item_name = state.get("bulk_waste_item")

        # 검색 타입: collection (수거 정보) | fee (수수료) | all
        search_type = state.get("bulk_waste_search_type", "all")

        input_dto = SearchBulkWasteInput(
            job_id=job_id,
            sigungu=sigungu,
            item_name=item_name,
            user_location=state.get("user_location"),
            search_type=search_type,
        )

        # 2. Command 실행 (정책/흐름은 Command에서)
        output = await command.execute(input_dto)

        # 3. output → state 변환
        if output.needs_location:
            # 위치 정보 필요 → HITL 트리거
            await event_publisher.notify_needs_input(
                task_id=job_id,
                input_type="location",
                message="🗑️ 대형폐기물 수거 정보는 지역마다 달라요.\n어느 지역(구)인지 알려주세요!",
                timeout=60,
            )
            await event_publisher.notify_stage(
                task_id=job_id,
                stage="bulk_waste",
                status="waiting",
                message="지역 정보 대기 중...",
            )
            return {
                **state,
                "bulk_waste_context": output.bulk_waste_context,
                "needs_location": True,
            }

        if not output.success:
            await event_publisher.notify_stage(
                task_id=job_id,
                stage="bulk_waste",
                status="failed",
                result={"error": output.error_message},
            )
            return {
                **state,
                "bulk_waste_context": output.bulk_waste_context,
                "bulk_waste_error": output.error_message,
            }

        # Progress: 완료 (UX)
        context = output.bulk_waste_context or {}
        has_collection = "collection" in context
        has_fees = "fees" in context

        result_message = "✅ 대형폐기물 정보를 찾았어요!"
        if has_collection and has_fees:
            result_message = "✅ 수거 방법과 수수료 정보를 찾았어요!"
        elif has_collection:
            result_message = "✅ 대형폐기물 수거 방법을 찾았어요!"
        elif has_fees:
            fee_count = context.get("fees", {}).get("item_count", 0)
            result_message = f"✅ {fee_count}개 품목의 수수료를 찾았어요!"

        await event_publisher.notify_stage(
            task_id=job_id,
            stage="bulk_waste",
            status="completed",
            progress=55,
            result={
                "has_collection": has_collection,
                "has_fees": has_fees,
            },
            message=result_message,
        )

        return {
            **state,
            "bulk_waste_context": output.bulk_waste_context,
        }

    # NodeExecutor로 래핑 (Policy 적용: timeout, retry, circuit breaker)
    executor = NodeExecutor.get_instance()

    async def bulk_waste_node(state: dict[str, Any]) -> dict[str, Any]:
        """LangGraph 노드 (Policy 적용됨).

        NodeExecutor가 다음을 처리:
        - Circuit Breaker 확인
        - Timeout 적용 (10000ms)
        - Retry (2회)
        - FAIL_FALLBACK 처리 (실패 시 대체 안내)
        """
        return await executor.execute(
            node_name="bulk_waste",
            node_func=_bulk_waste_node_inner,
            state=state,
        )

    return bulk_waste_node


__all__ = ["create_bulk_waste_node"]
