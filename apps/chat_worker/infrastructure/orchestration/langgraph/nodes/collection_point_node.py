"""Collection Point Node - LangGraph 어댑터.

얇은 어댑터: state 변환 + Command 호출 + progress notify (UX).
정책/흐름은 SearchCollectionPointCommand(Application)에서 처리.

Clean Architecture:
- Node(Adapter): 이 파일 - LangGraph glue code
- Command(UseCase): SearchCollectionPointCommand - 정책/흐름
- Port: CollectionPointClientPort - HTTP API 호출

Function Calling:
- LLM이 사용자 메시지에서 수거함 검색 파라미터를 동적으로 추출
- 수거 품목(의류, 폐건전지, 형광등, 폐휴대폰) 자동 파악
- 검색 반경 자동 설정

Channel Separation:
- 출력 채널: collection_point_context
- Reducer: priority_preemptive_reducer
- spread 금지: {"collection_point_context": create_context(...)} 형태로 반환

사용 시나리오:
1. "폐휴대폰 어디서 버려?" → 근처 수거함 위치 안내
2. "폐건전지 수거함" → 수거함 검색
3. 특정 지역 수거함 검색

Flow:
    Router → collection_point (Function Calling) → API 실행 → Answer
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from chat_worker.application.commands.search_collection_point_command import (
    SearchCollectionPointCommand,
    SearchCollectionPointInput,
)
from chat_worker.infrastructure.orchestration.langgraph.context_helper import (
    create_context,
    create_error_context,
)
from chat_worker.infrastructure.orchestration.langgraph.nodes.node_executor import (
    NodeExecutor,
)

if TYPE_CHECKING:
    from chat_worker.application.ports.collection_point_client import (
        CollectionPointClientPort,
    )
    from chat_worker.application.ports.events import ProgressNotifierPort
    from chat_worker.application.ports.llm import LLMClientPort

logger = logging.getLogger(__name__)

# Function Definition for OpenAI Function Calling
COLLECTION_POINT_FUNCTION = {
    "name": "find_collection_points",
    "description": "KECO API로 주변 의류수거함, 폐건전지 수거함 등을 찾습니다.",
    "parameters": {
        "type": "object",
        "properties": {
            "item_type": {
                "type": "string",
                "enum": ["clothes", "battery", "fluorescent_lamp", "phone"],
                "description": "수거 품목. clothes=의류, battery=폐건전지, fluorescent_lamp=형광등, phone=폐휴대폰",
            },
            "search_radius_km": {
                "type": "number",
                "description": "검색 반경(킬로미터). 기본값 2km",
                "default": 2.0,
            },
        },
        "required": ["item_type"],
    },
}


def create_collection_point_node(
    collection_point_client: "CollectionPointClientPort",
    event_publisher: "ProgressNotifierPort",
    llm: "LLMClientPort",
):
    """수거함 노드 팩토리.

    Node는 LangGraph 어댑터:
    - state → input DTO 변환
    - LLM Function Calling으로 파라미터 추출
    - Command(UseCase) 호출
    - output → state 변환
    - progress notify (UX)

    Args:
        collection_point_client: 수거함 클라이언트
        event_publisher: 이벤트 발행기
        llm: LLM 클라이언트 (Function Calling용)

    Returns:
        collection_point_node 함수
    """
    # Command(UseCase) 인스턴스 생성 - Port 조립
    command = SearchCollectionPointCommand(collection_point_client=collection_point_client)

    async def _collection_point_node_inner(state: dict[str, Any]) -> dict[str, Any]:
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
            stage="collection_point",
            status="started",
            progress=45,
            message="수거함 위치 검색 중",
        )

        # 1. LLM Function Calling으로 파라미터 추출
        system_prompt = """사용자의 메시지에서 수거함 검색에 필요한 정보를 추출하세요.

지침:
- 수거 품목(item_type) 파악: 의류, 폐건전지, 형광등, 폐휴대폰
- 검색 반경(search_radius_km)은 명시되지 않으면 2km 사용
- 사용자가 "주변", "근처" 등의 키워드를 사용하면 주변 검색 의도입니다.

예시:
- "폐휴대폰 어디서 버려?" → item_type: "phone", search_radius_km: 2.0
- "3km 이내 의류수거함" → item_type: "clothes", search_radius_km: 3.0
- "폐건전지 수거함" → item_type: "battery", search_radius_km: 2.0
- "형광등 버리는 곳" → item_type: "fluorescent_lamp", search_radius_km: 2.0
"""

        try:
            func_name, func_args = await llm.generate_function_call(
                prompt=message,
                functions=[COLLECTION_POINT_FUNCTION],
                system_prompt=system_prompt,
                function_call={"name": "find_collection_points"},  # 강제 호출
            )

            if not func_args:
                # Function call 실패 → fallback: 메시지에서 추출
                logger.warning(
                    "Function call failed, using fallback",
                    extra={"job_id": job_id, "user_message": message},
                )
                # 기본값 사용
                func_args = {
                    "item_type": "clothes",  # 기본값
                    "search_radius_km": 2.0,
                }

        except Exception as e:
            # LLM 호출 실패 → fallback
            logger.error(
                f"Function calling error: {e}",
                extra={"job_id": job_id, "user_message": message},
            )
            await event_publisher.notify_stage(
                task_id=job_id,
                stage="collection_point",
                status="failed",
                result={"error": "파라미터 추출 실패"},
            )
            return {
                "collection_point_context": create_error_context(
                    producer="collection_point",
                    job_id=job_id,
                    error=f"수거함 검색 정보를 추출할 수 없습니다: {str(e)}",
                ),
            }

        # 2. Function call 결과 → input DTO 변환
        # item_type을 name_keyword로 매핑 (기존 로직 호환)
        item_type_map = {
            "clothes": "의류",
            "battery": "폐건전지",
            "fluorescent_lamp": "형광등",
            "phone": "폐휴대폰",
        }
        item_type = func_args.get("item_type", "clothes")
        name_keyword = item_type_map.get(item_type, item_type)

        input_dto = SearchCollectionPointInput(
            job_id=job_id,
            address_keyword=state.get("collection_point_address"),
            name_keyword=name_keyword,
            user_location=state.get("user_location"),
            limit=5,
        )

        # 3. Command 실행 (정책/흐름은 Command에서)
        output = await command.execute(input_dto)

        # 4. output → state 변환
        if output.needs_location:
            # 위치 정보 필요 → HITL 트리거
            await event_publisher.notify_needs_input(
                task_id=job_id,
                input_type="location",
                message="수거함 위치를 찾으려면 지역 정보가 필요합니다. 지역(구)을 알려주세요.",
                timeout=60,
            )
            await event_publisher.notify_stage(
                task_id=job_id,
                stage="collection_point",
                status="waiting",
                message="지역 정보 대기 중...",
            )
            return {
                "collection_point_context": create_context(
                    data=output.collection_point_context or {"needs_location": True},
                    producer="collection_point",
                    job_id=job_id,
                ),
            }

        if not output.success:
            await event_publisher.notify_stage(
                task_id=job_id,
                stage="collection_point",
                status="failed",
                result={"error": output.error_message},
            )
            return {
                "collection_point_context": create_error_context(
                    producer="collection_point",
                    job_id=job_id,
                    error=output.error_message or "수거함 검색 실패",
                ),
            }

        # Progress: 완료 (UX)
        context = output.collection_point_context or {}
        found = context.get("found", False)
        count = context.get("count", 0)

        result_message = "수거함 정보 조회 완료"
        if found:
            result_message = f"{count}곳 수거함 검색 완료"
        elif context.get("type") == "guide":
            result_message = "지역 정보 필요"

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
            "collection_point_context": create_context(
                data=output.collection_point_context or {},
                producer="collection_point",
                job_id=job_id,
            ),
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
