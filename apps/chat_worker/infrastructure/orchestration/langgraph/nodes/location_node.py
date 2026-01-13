"""Location Subagent Node - Orchestration Only.

LangGraph 파이프라인의 위치 검색 노드입니다.

노드 책임: 이벤트 발행 + 서비스 호출 + state 업데이트
비즈니스 로직: LocationService, HumanInputService에 위임

Clean Architecture:
- Node: Orchestration만 담당 (이 파일)
- Service: LocationService (검색 + 컨텍스트 변환)
- Service: HumanInputService (Human-in-the-Loop)
- Domain: LocationData, HumanInputResponse (Value Objects)
- Port: LocationClientPort (API 호출)

흐름 (Human-in-the-Loop):
1. 진행 이벤트 발행
2. 위치 확인 (state 또는 Human-in-the-Loop)
3. LocationService로 주변 센터 검색
4. state 업데이트
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from chat_worker.application.integrations.location.services import LocationService
from chat_worker.domain import LocationData

if TYPE_CHECKING:
    from chat_worker.application.integrations.location.ports import LocationClientPort
    from chat_worker.application.interaction.ports import InputRequesterPort
    from chat_worker.application.ports.events import ProgressNotifierPort

logger = logging.getLogger(__name__)


def create_location_subagent_node(
    location_client: "LocationClientPort",
    event_publisher: "ProgressNotifierPort",
    input_requester: "InputRequesterPort | None" = None,
):
    """Location Subagent 노드 생성.

    노드는 thin wrapper로:
    1. 이벤트 발행
    2. LocationService 호출 (비즈니스 로직 위임)
    3. state 업데이트

    Args:
        location_client: Location gRPC/HTTP 클라이언트
        event_publisher: 이벤트 발행자 (SSE 진행 상황)
        input_requester: Human-in-the-Loop 입력 요청자 (Port)

    Returns:
        LangGraph 노드 함수
    """
    # Service 인스턴스들 (비즈니스 로직 담당)
    # Note: HumanInteractionService는 InteractionStateStorePort도 필요하므로
    #       여기서는 직접 생성하지 않고 DI로 주입받아야 함
    #       현재는 input_requester만 사용하여 간단히 처리

    location_service = LocationService(client=location_client)

    async def location_subagent(state: dict[str, Any]) -> dict[str, Any]:
        """주변 재활용 센터를 검색합니다.

        노드 책임 (Orchestration):
        1. 이벤트 발행 (진행 상황)
        2. 서비스 호출 (비즈니스 로직 위임)
        3. state 업데이트
        """
        job_id = state.get("job_id", "")
        user_location_dict = state.get("user_location")

        # 1. 이벤트: 시작
        await event_publisher.notify_stage(
            task_id=job_id,
            stage="location",
            status="processing",
            progress=50,
            message="📍 위치 정보 확인 중...",
        )

        # 2. LocationService 호출 (Human-in-the-Loop 포함)
        try:
            centers, error_msg = await location_service.search_with_human_input(
                job_id=job_id,
                user_location=user_location_dict,
                radius=5000,  # 5km 반경
                limit=5,  # 최대 5개
            )

            # 에러 또는 스킵
            if error_msg:
                return {
                    **state,
                    "location_context": None,
                    "subagent_error": error_msg,
                }

            if centers is None:
                # Human-in-the-Loop 취소/타임아웃
                await event_publisher.notify_stage(
                    task_id=job_id,
                    stage="location",
                    status="skipped",
                    message="위치 정보 없이 진행합니다.",
                )
                return {
                    **state,
                    "location_context": None,
                    "location_skipped": True,
                }

            # 3. 컨텍스트 구성 (Service의 메서드 사용)
            location_data = _extract_location_data(user_location_dict)
            context = LocationService.to_answer_context(
                locations=centers,
                user_location=location_data,
            )

            logger.info(
                "Location search completed",
                extra={
                    "job_id": job_id,
                    "count": len(centers),
                },
            )

            return {
                **state,
                "location_context": context,
            }

        except Exception as e:
            logger.error(
                "Location service call failed",
                extra={"job_id": job_id, "error": str(e)},
            )
            return {
                **state,
                "location_context": None,
                "subagent_error": "주변 센터 정보를 가져오는 데 실패했어요.",
            }

    return location_subagent


def _extract_location_data(user_location_dict: dict[str, Any] | None) -> LocationData | None:
    """사용자 위치 dict에서 LocationData를 추출."""
    if not user_location_dict:
        return None

    try:
        data = LocationData.from_dict(user_location_dict)
        return data if data.is_valid() else None
    except (KeyError, ValueError):
        return None
