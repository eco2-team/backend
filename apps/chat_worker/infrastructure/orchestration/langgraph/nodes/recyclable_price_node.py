"""Recyclable Price Node - LangGraph 어댑터.

얇은 어댑터: state 변환 + Command 호출 + progress notify (UX).
정책/흐름은 SearchRecyclablePriceCommand(Application)에서 처리.

Clean Architecture:
- Node(Adapter): 이 파일 - LangGraph glue code
- Command(UseCase): SearchRecyclablePriceCommand - 정책/흐름
- Service: RecyclablePriceService - 순수 비즈니스 로직

사용 시나리오:
1. 재활용품 시세 문의 (예: "캔 한 개 얼마예요?")
2. 카테고리별 시세 조회 (예: "플라스틱 시세 알려줘")
3. 전체 시세 조회

Flow:
    Router → recyclable_price → Answer
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from chat_worker.application.commands.search_recyclable_price_command import (
    SearchRecyclablePriceCommand,
    SearchRecyclablePriceInput,
)
from chat_worker.infrastructure.orchestration.langgraph.nodes.node_executor import (
    NodeExecutor,
)

if TYPE_CHECKING:
    from chat_worker.application.ports.events import ProgressNotifierPort
    from chat_worker.application.ports.recyclable_price_client import (
        RecyclablePriceClientPort,
    )

logger = logging.getLogger(__name__)


def create_recyclable_price_node(
    price_client: "RecyclablePriceClientPort",
    event_publisher: "ProgressNotifierPort",
):
    """재활용자원 시세 노드 팩토리.

    Node는 LangGraph 어댑터:
    - state → input DTO 변환
    - Command(UseCase) 호출
    - output → state 변환
    - progress notify (UX)

    Args:
        price_client: 재활용자원 가격 클라이언트
        event_publisher: 이벤트 발행기

    Returns:
        recyclable_price_node 함수
    """
    # Command(UseCase) 인스턴스 생성 - Port 조립
    command = SearchRecyclablePriceCommand(price_client=price_client)

    async def _recyclable_price_node_inner(state: dict[str, Any]) -> dict[str, Any]:
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
            stage="recyclable_price",
            status="started",
            progress=45,
            message="재활용자원 시세 조회 중",
        )

        # 1. state → input DTO 변환
        # 품목명: recyclable_item 우선, 없으면 message에서 추출
        item_name = state.get("recyclable_item")
        message = state.get("message", "")

        input_dto = SearchRecyclablePriceInput(
            job_id=job_id,
            item_name=item_name,
            category=state.get("recyclable_category"),
            region=state.get("recyclable_region"),
            message=message,
        )

        # 2. Command 실행 (정책/흐름은 Command에서)
        output = await command.execute(input_dto)

        # 3. output → state 변환
        if not output.success:
            await event_publisher.notify_stage(
                task_id=job_id,
                stage="recyclable_price",
                status="failed",
                result={"error": output.error_message},
            )
            return {
                **state,
                "recyclable_price_context": output.price_context,
                "recyclable_price_error": output.error_message,
            }

        # Progress: 완료 (UX)
        context = output.price_context or {}
        found = context.get("found", False)
        count = context.get("count", 0)

        result_message = "재활용자원 시세 조회 완료"
        if found:
            result_message = f"{count}개 품목 시세 조회 완료"
        elif context.get("type") == "guide":
            result_message = "품목 정보 필요"

        await event_publisher.notify_stage(
            task_id=job_id,
            stage="recyclable_price",
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
            "recyclable_price_context": output.price_context,
        }

    # NodeExecutor로 래핑 (Policy 적용: timeout, retry, circuit breaker)
    executor = NodeExecutor.get_instance()

    async def recyclable_price_node(state: dict[str, Any]) -> dict[str, Any]:
        """LangGraph 노드 (Policy 적용됨).

        NodeExecutor가 다음을 처리:
        - Circuit Breaker 확인
        - Timeout 적용 (10000ms)
        - Retry (2회)
        - FAIL_FALLBACK 처리 (실패 시 대체 안내)
        """
        return await executor.execute(
            node_name="recyclable_price",
            node_func=_recyclable_price_node_inner,
            state=state,
        )

    return recyclable_price_node


__all__ = ["create_recyclable_price_node"]
