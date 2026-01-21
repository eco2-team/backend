"""Bulk Waste Node - LangGraph 어댑터.

얇은 어댑터: state 변환 + Command 호출 + progress notify (UX).
정책/흐름은 SearchBulkWasteCommand(Application)에서 처리.

Clean Architecture:
- Node(Adapter): 이 파일 - LangGraph glue code
- Command(UseCase): SearchBulkWasteCommand - 정책/흐름
- Service: BulkWasteService - 순수 비즈니스 로직

Function Calling:
- LLM이 사용자 메시지에서 대형폐기물 품목명과 지역을 동적으로 추출
- item_name(필수), region(선택) 자동 파싱
- Heuristic 대신 LLM 기반 파라미터 결정

Channel Separation:
- 출력 채널: bulk_waste_context
- Reducer: priority_preemptive_reducer
- spread 금지: {"bulk_waste_context": create_context(...)} 형태로 반환

사용 시나리오:
1. 대형폐기물 수거 신청 방법 안내
2. 대형폐기물 품목별 수수료 조회
3. 지역별 배출 방법 안내

Flow:
    Router → bulk_waste (Function Calling) → API 실행 → Answer
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from chat_worker.application.commands.search_bulk_waste_command import (
    SearchBulkWasteCommand,
    SearchBulkWasteInput,
)
from chat_worker.infrastructure.orchestration.langgraph.context_helper import (
    create_context,
    create_error_context,
)
from chat_worker.infrastructure.orchestration.langgraph.nodes.node_executor import (
    NodeExecutor,
)

if TYPE_CHECKING:
    from chat_worker.application.ports.bulk_waste_client import BulkWasteClientPort
    from chat_worker.application.ports.events import ProgressNotifierPort
    from chat_worker.application.ports.llm import LLMClientPort

logger = logging.getLogger(__name__)

# Function Definition for OpenAI Function Calling
BULK_WASTE_FUNCTION = {
    "name": "search_bulk_waste_info",
    "description": "지자체 API로 대형폐기물 처리 방법과 수수료를 조회합니다.",
    "parameters": {
        "type": "object",
        "properties": {
            "item_name": {
                "type": "string",
                "description": "대형폐기물 품목명 (예: '냉장고', '소파', '침대', '에어컨', '세탁기')",
            },
            "region": {
                "type": "string",
                "description": "지역명 (예: '서울시 강남구'). 사용자가 명시하지 않으면 null",
            },
        },
        "required": ["item_name"],
    },
}


def create_bulk_waste_node(
    bulk_waste_client: "BulkWasteClientPort",
    event_publisher: "ProgressNotifierPort",
    llm: "LLMClientPort",
):
    """대형폐기물 노드 팩토리.

    Node는 LangGraph 어댑터:
    - state → input DTO 변환
    - LLM Function Calling으로 파라미터 추출
    - Command(UseCase) 호출
    - output → state 변환
    - progress notify (UX)

    Args:
        bulk_waste_client: 대형폐기물 클라이언트
        event_publisher: 이벤트 발행기
        llm: LLM 클라이언트 (Function Calling용)

    Returns:
        bulk_waste_node 함수
    """
    # Command(UseCase) 인스턴스 생성 - Port 조립
    command = SearchBulkWasteCommand(bulk_waste_client=bulk_waste_client)

    async def _bulk_waste_node_inner(state: dict[str, Any]) -> dict[str, Any]:
        """실제 노드 로직 (NodeExecutor가 래핑).

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
            stage="bulk_waste",
            status="started",
            progress=45,
            message="대형폐기물 정보 조회 중",
        )

        # 1. LLM Function Calling으로 파라미터 추출
        system_prompt = """사용자의 메시지에서 대형폐기물 정보 조회에 필요한 정보를 추출하세요.

지침:
- item_name: 대형폐기물 품목명 (냉장고, 소파, 침대, 에어컨, 세탁기 등)
- region: 지역명 (예: '서울시 강남구', '부산시 해운대구'). 사용자가 명시하지 않으면 null
- 사용자가 품목명만 언급하고 지역을 말하지 않으면 region은 null로 설정

예시:
- "냉장고 버리는 방법 알려줘" → item_name: "냉장고", region: null
- "강남구 소파 수수료" → item_name: "소파", region: "서울시 강남구"
- "서울시 마포구에서 침대 버릴 때" → item_name: "침대", region: "서울시 마포구"
- "에어컨 처리 비용" → item_name: "에어컨", region: null
"""

        item_name = None
        region = None

        try:
            func_name, func_args = await llm.generate_function_call(
                prompt=message,
                functions=[BULK_WASTE_FUNCTION],
                system_prompt=system_prompt,
                function_call={"name": "search_bulk_waste_info"},  # 강제 호출
            )

            if func_args:
                item_name = func_args.get("item_name")
                region = func_args.get("region")
                logger.info(
                    "Function call extracted parameters",
                    extra={
                        "job_id": job_id,
                        "item_name": item_name,
                        "region": region,
                    },
                )
            else:
                # Function call 실패 → fallback: state에서 가져오기
                logger.warning(
                    "Function call failed, using state fallback",
                    extra={"job_id": job_id, "user_message": message},
                )
                item_name = state.get("bulk_waste_item")
                region = state.get("bulk_waste_sigungu")

        except Exception as e:
            # LLM 호출 실패 → fallback: state에서 가져오기
            logger.error(
                f"Function calling error: {e}",
                extra={"job_id": job_id, "user_message": message},
            )
            item_name = state.get("bulk_waste_item")
            region = state.get("bulk_waste_sigungu")

        # 2. region 결정: LLM 추출 → state → user_location → HITL
        sigungu = region or state.get("bulk_waste_sigungu")

        # 3. 검색 타입: collection (수거 정보) | fee (수수료) | all
        search_type = state.get("bulk_waste_search_type", "all")

        # 4. input DTO 변환
        input_dto = SearchBulkWasteInput(
            job_id=job_id,
            sigungu=sigungu,
            item_name=item_name,
            user_location=state.get("user_location"),
            search_type=search_type,
        )

        # 5. Command 실행 (정책/흐름은 Command에서)
        output = await command.execute(input_dto)

        # 6. output → state 변환
        if output.needs_location:
            # 위치 정보 필요 → HITL 트리거
            await event_publisher.notify_needs_input(
                task_id=job_id,
                input_type="location",
                message="대형폐기물 수거 정보는 지역마다 다릅니다. 지역(구)을 알려주세요.",
                timeout=60,
            )
            await event_publisher.notify_stage(
                task_id=job_id,
                stage="bulk_waste",
                status="waiting",
                message="지역 정보 대기 중...",
            )
            return {
                "bulk_waste_context": create_context(
                    data=output.bulk_waste_context or {"needs_location": True},
                    producer="bulk_waste",
                    job_id=job_id,
                ),
            }

        if not output.success:
            await event_publisher.notify_stage(
                task_id=job_id,
                stage="bulk_waste",
                status="failed",
                result={"error": output.error_message},
            )
            return {
                "bulk_waste_context": create_error_context(
                    producer="bulk_waste",
                    job_id=job_id,
                    error=output.error_message or "대형폐기물 정보 조회 실패",
                ),
            }

        # Progress: 완료 (UX)
        context = output.bulk_waste_context or {}
        has_collection = "collection" in context
        has_fees = "fees" in context

        result_message = "대형폐기물 정보 조회 완료"
        if has_collection and has_fees:
            result_message = "수거 방법 및 수수료 정보 조회 완료"
        elif has_collection:
            result_message = "대형폐기물 수거 방법 조회 완료"
        elif has_fees:
            fee_count = context.get("fees", {}).get("item_count", 0)
            result_message = f"{fee_count}개 품목 수수료 조회 완료"

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
            "bulk_waste_context": create_context(
                data=output.bulk_waste_context or {},
                producer="bulk_waste",
                job_id=job_id,
            ),
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
