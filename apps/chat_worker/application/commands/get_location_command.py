"""Get Location Command.

주변 재활용 센터/제로웨이스트샵 검색 UseCase.

Clean Architecture:
- Command(UseCase): 이 파일 - Port 호출, 오케스트레이션
- Service: LocationService - 순수 비즈니스 로직 (컨텍스트 변환, 검증)
- Port: LocationClientPort - gRPC API 호출
- Node(Adapter): location_node.py - LangGraph glue

구조:
- Command: 위치 검증, API 호출, Service 호출, 오케스트레이션
- Service: 컨텍스트 변환, 결과 포맷팅 (Port 의존 없음)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from chat_worker.application.services.location_service import LocationService
from chat_worker.domain import LocationData

if TYPE_CHECKING:
    from chat_worker.application.ports.location_client import LocationClientPort

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GetLocationInput:
    """Command 입력 DTO."""

    job_id: str
    user_location: dict[str, Any] | None = None
    search_type: str = "recycling"  # recycling | zerowaste
    radius: int = 5000  # 검색 반경 (미터)
    limit: int = 5  # 최대 결과 수


@dataclass
class GetLocationOutput:
    """Command 출력 DTO."""

    success: bool
    location_context: dict[str, Any] | None = None
    needs_location: bool = False  # 위치 정보 필요 여부 (HITL 트리거)
    error_message: str | None = None
    events: list[str] = field(default_factory=list)


class GetLocationCommand:
    """주변 위치 검색 Command (UseCase).

    Port 호출 + 오케스트레이션:
    1. 위치 검증 (Service - 순수 로직)
    2. API 호출 (LocationClientPort)
    3. 컨텍스트 변환 (Service - 순수 로직)

    Port 주입:
    - location_client: 위치 검색 API 클라이언트
    """

    def __init__(
        self,
        location_client: "LocationClientPort",
    ) -> None:
        """Command 초기화.

        Args:
            location_client: Location gRPC 클라이언트
        """
        self._location_client = location_client

    async def execute(self, input_dto: GetLocationInput) -> GetLocationOutput:
        """Command 실행.

        Args:
            input_dto: 입력 DTO

        Returns:
            출력 DTO
        """
        events: list[str] = []

        # 1. 위치 데이터 추출 및 검증 (Service - 순수 로직)
        location_data = self._extract_location_data(input_dto.user_location)

        if not LocationService.validate_location(location_data):
            events.append("location_not_provided")
            return GetLocationOutput(
                success=True,  # 비즈니스 로직상 성공 (위치 없음도 정상 케이스)
                location_context=LocationService.build_no_location_context(),
                needs_location=True,
                events=events,
            )

        events.append("location_validated")

        # 2. Location API 호출 (Command에서 Port 호출)
        try:
            if input_dto.search_type == "zerowaste":
                centers = await self._location_client.search_zerowaste_shops(
                    lat=location_data.latitude,
                    lon=location_data.longitude,
                    radius=input_dto.radius,
                    limit=input_dto.limit,
                )
                events.append("zerowaste_api_called")
            else:
                centers = await self._location_client.search_recycling_centers(
                    lat=location_data.latitude,
                    lon=location_data.longitude,
                    radius=input_dto.radius,
                    limit=input_dto.limit,
                )
                events.append("recycling_api_called")

            logger.info(
                "Location API called",
                extra={
                    "job_id": input_dto.job_id,
                    "search_type": input_dto.search_type,
                    "count": len(centers),
                },
            )

        except Exception as e:
            logger.error(
                "Location API call failed",
                extra={"job_id": input_dto.job_id, "error": str(e)},
            )
            events.append("location_api_error")
            return GetLocationOutput(
                success=False,
                error_message="주변 센터 정보를 가져오는 데 실패했어요.",
                events=events,
            )

        # 3. 컨텍스트 변환 (Service - 순수 로직)
        if not centers:
            events.append("location_not_found")
            context = LocationService.build_not_found_context(location_data)
        else:
            events.append("location_found")
            context = LocationService.to_answer_context(
                locations=centers,
                user_location=location_data,
            )

        logger.info(
            "Location search completed",
            extra={
                "job_id": input_dto.job_id,
                "found": len(centers) > 0,
                "count": len(centers),
            },
        )

        return GetLocationOutput(
            success=True,
            location_context=context,
            events=events,
        )

    @staticmethod
    def _extract_location_data(
        user_location_dict: dict[str, Any] | None,
    ) -> LocationData | None:
        """사용자 위치 dict에서 LocationData를 추출.

        Args:
            user_location_dict: 사용자 위치 딕셔너리

        Returns:
            LocationData 또는 None
        """
        if not user_location_dict:
            return None

        try:
            data = LocationData.from_dict(user_location_dict)
            return data if data.is_valid() else None
        except (KeyError, ValueError):
            return None
