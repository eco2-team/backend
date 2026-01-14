"""Location Service - 위치 비즈니스 로직.

Location API 호출 및 컨텍스트 변환을 담당.

Clean Architecture:
- Service: 비즈니스 로직 (이 파일)
- Port: LocationClientPort (API 호출만)
- DTO: LocationDTO
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from chat_worker.domain import LocationData

if TYPE_CHECKING:
    from chat_worker.application.integrations.location.ports import (
        LocationClientPort,
        LocationDTO,
    )

logger = logging.getLogger(__name__)


class LocationService:
    """위치 비즈니스 로직 서비스.

    책임:
    - 위치 검색 (Port 호출)
    - 컨텍스트 변환 (to_answer_context)

    Human-in-the-Loop는 interaction/에서 별도 처리.
    여기서는 검색 로직만 담당.
    """

    def __init__(self, client: "LocationClientPort"):
        self._client = client

    async def search_recycling_centers(
        self,
        location: LocationData,
        radius: int = 5000,
        limit: int = 5,
    ) -> list["LocationDTO"]:
        """주변 재활용 센터 검색.

        Args:
            location: 위치 정보 (Domain VO)
            radius: 반경 (미터)
            limit: 최대 반환 개수

        Returns:
            재활용 센터 목록
        """
        centers = await self._client.search_recycling_centers(
            lat=location.latitude,
            lon=location.longitude,
            radius=radius,
            limit=limit,
        )

        logger.info(
            "Recycling centers found",
            extra={
                "lat": location.latitude,
                "lon": location.longitude,
                "count": len(centers),
            },
        )

        return centers

    async def search_zerowaste_shops(
        self,
        location: LocationData,
        radius: int = 5000,
        limit: int = 5,
    ) -> list["LocationDTO"]:
        """주변 제로웨이스트샵 검색."""
        return await self._client.search_zerowaste_shops(
            lat=location.latitude,
            lon=location.longitude,
            radius=radius,
            limit=limit,
        )

    @staticmethod
    def to_answer_context(
        locations: list["LocationDTO"],
        user_location: LocationData | None = None,
    ) -> dict[str, Any]:
        """Answer 노드용 컨텍스트 생성."""
        context: dict[str, Any] = {
            "found": len(locations) > 0,
            "count": len(locations),
        }

        if user_location:
            context["user_location"] = user_location.to_dict()

        if locations:
            context["centers"] = [
                {
                    "name": loc.name,
                    "address": loc.road_address,
                    "distance": loc.distance_text,
                    "is_open": loc.is_open,
                    "phone": loc.phone,
                    "categories": loc.pickup_categories,
                }
                for loc in locations
            ]
        else:
            context["message"] = "주변에 재활용 센터를 찾지 못했어요."

        return context
