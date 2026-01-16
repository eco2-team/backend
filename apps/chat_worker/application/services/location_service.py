"""Location Service - 순수 비즈니스 로직.

Port 의존 없이 순수 로직만 담당:
- 컨텍스트 변환 (to_answer_context)
- 결과 검증

Port 호출(API)은 Node에서 담당.

Clean Architecture:
- Service: 이 파일 (순수 로직, Port 의존 없음)
- Node: location_node.py (Port 호출, 오케스트레이션)
- DTO: LocationDTO
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from chat_worker.domain import LocationData

if TYPE_CHECKING:
    from chat_worker.application.ports.location_client import LocationDTO

logger = logging.getLogger(__name__)


class LocationService:
    """위치 비즈니스 로직 서비스 (순수 로직).

    Port 의존 없이 순수 비즈니스 로직만 담당:
    - 컨텍스트 변환 (to_answer_context)
    - 결과 검증

    API 호출은 Node에서 담당.
    """

    @staticmethod
    def to_answer_context(
        locations: list["LocationDTO"],
        user_location: LocationData | None = None,
    ) -> dict[str, Any]:
        """Answer 노드용 컨텍스트 생성.

        Args:
            locations: 위치 DTO 목록
            user_location: 사용자 위치 (Domain VO)

        Returns:
            Answer 노드용 컨텍스트 딕셔너리
        """
        context: dict[str, Any] = {
            "found": len(locations) > 0,
            "count": len(locations),
        }

        if user_location:
            context["user_location"] = user_location.to_dict()

        if locations:
            context["centers"] = [
                LocationService._location_to_dict(loc) for loc in locations
            ]
        else:
            context["message"] = "주변에 재활용 센터를 찾지 못했어요."

        return context

    @staticmethod
    def _location_to_dict(loc: "LocationDTO") -> dict[str, Any]:
        """LocationDTO를 딕셔너리로 변환.

        Args:
            loc: 위치 DTO

        Returns:
            딕셔너리
        """
        return {
            "name": loc.name,
            "address": loc.road_address,
            "distance": loc.distance_text,
            "is_open": loc.is_open,
            "phone": loc.phone,
            "categories": loc.pickup_categories,
        }

    @staticmethod
    def validate_location(location: LocationData | None) -> bool:
        """위치 유효성 검증.

        Args:
            location: 위치 데이터 (None일 수 있음)

        Returns:
            유효 여부
        """
        if location is None:
            return False
        return location.latitude != 0.0 and location.longitude != 0.0

    @staticmethod
    def build_no_location_context() -> dict[str, Any]:
        """위치 정보 없음 컨텍스트 생성.

        Returns:
            위치 정보 없음 컨텍스트
        """
        return {
            "found": False,
            "count": 0,
            "error": "location_not_provided",
            "message": "위치 정보가 필요해요. 위치를 공유해주시겠어요? 📍",
        }

    @staticmethod
    def build_not_found_context(user_location: LocationData) -> dict[str, Any]:
        """결과 없음 컨텍스트 생성.

        Args:
            user_location: 사용자 위치

        Returns:
            결과 없음 컨텍스트
        """
        return {
            "found": False,
            "count": 0,
            "user_location": user_location.to_dict(),
            "message": "주변에 재활용 센터를 찾지 못했어요. 검색 범위를 넓혀볼까요?",
        }
