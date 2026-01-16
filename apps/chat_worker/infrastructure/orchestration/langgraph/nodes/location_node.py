"""Location Subagent Node - LangGraph 어댑터.

얇은 어댑터: state 변환 + Command 호출 + progress notify (UX).
정책/흐름은 GetLocationCommand(Application)에서 처리.

Clean Architecture:
- Node(Adapter): 이 파일 - LangGraph glue code
- Command(UseCase): GetLocationCommand - 정책/흐름
- Service: LocationService - 순수 비즈니스 로직

Production Architecture:
- NodeExecutor로 Policy 적용 (timeout, retry, circuit breaker)
- location 노드는 FAIL_FALLBACK (필수 컨텍스트, 실패 시 대체 안내)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from chat_worker.application.commands.get_location_command import (
    GetLocationCommand,
    GetLocationInput,
)
from chat_worker.infrastructure.orchestration.langgraph.nodes.node_executor import (
    NodeExecutor,
)

if TYPE_CHECKING:
    from chat_worker.application.ports.events import ProgressNotifierPort
    from chat_worker.application.ports.location_client import LocationClientPort

logger = logging.getLogger(__name__)


def create_location_subagent_node(
    location_client: "LocationClientPort",
    event_publisher: "ProgressNotifierPort",
):
    """Location Subagent 노드 생성.

    Node는 LangGraph 어댑터:
    - state → input DTO 변환
    - Command(UseCase) 호출
    - output → state 변환
    - progress notify (UX)

    Args:
        location_client: Location gRPC 클라이언트
        event_publisher: 이벤트 발행자 (SSE 진행 상황)

    Returns:
        LangGraph 노드 함수
    """
    # Command(UseCase) 인스턴스 생성 - Port 조립
    command = GetLocationCommand(location_client=location_client)

    async def _location_subagent_inner(state: dict[str, Any]) -> dict[str, Any]:
        """실제 노드 로직 (NodeExecutor가 래핑).

        역할:
        1. state에서 값 추출 (LangGraph glue)
        2. Command 호출 (정책/흐름 위임)
        3. output → state 변환

        Args:
            state: 현재 LangGraph 상태

        Returns:
            업데이트된 상태
        """
        job_id = state.get("job_id", "")

        # Progress: 시작 (UX)
        await event_publisher.notify_stage(
            task_id=job_id,
            stage="location",
            status="processing",
            progress=50,
            message="위치 정보 확인 중",
        )

        # 1. state → input DTO 변환
        input_dto = GetLocationInput(
            job_id=job_id,
            user_location=state.get("user_location"),
            search_type="recycling",  # TODO: intent에 따라 zerowaste 선택 가능
            radius=5000,
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
                message="주변 센터를 찾으려면 위치 정보가 필요합니다. 위치 권한을 허용해주세요.",
                timeout=60,
            )
            await event_publisher.notify_stage(
                task_id=job_id,
                stage="location",
                status="skipped",
                message="위치 정보 없이 진행합니다.",
            )
            return {
                **state,
                "location_context": output.location_context,
                "location_skipped": True,
                "needs_location": True,
            }

        if not output.success:
            return {
                **state,
                "location_context": None,
                "subagent_error": output.error_message,
            }

        # Progress: 완료 (UX)
        found = output.location_context.get("found", False)
        await event_publisher.notify_stage(
            task_id=job_id,
            stage="location",
            status="completed",
            progress=60,
            result={"found": found},
            message="위치 정보 조회 완료" if found else "위치 정보 조회 완료 (결과 없음)",
        )

        return {
            **state,
            "location_context": output.location_context,
        }

    # NodeExecutor로 래핑 (Policy 적용: timeout, retry, circuit breaker)
    executor = NodeExecutor.get_instance()

    async def location_subagent(state: dict[str, Any]) -> dict[str, Any]:
        """LangGraph 노드 (Policy 적용됨).

        NodeExecutor가 다음을 처리:
        - Circuit Breaker 확인
        - Timeout 적용 (3000ms)
        - Retry (2회)
        - FAIL_FALLBACK 처리 (실패 시 대체 안내)
        """
        return await executor.execute(
            node_name="location",
            node_func=_location_subagent_inner,
            state=state,
        )

    return location_subagent
