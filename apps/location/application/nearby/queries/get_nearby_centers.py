"""Get Nearby Centers Query.

주변 재활용 센터를 조회하는 Query(지휘자)입니다.
Port를 통해 Infrastructure와 통신하고, Service에 순수 로직을 위임합니다.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from location.application.nearby.dto import LocationEntryDTO, SearchRequest
from location.application.nearby.services import (
    CategoryClassifierService,
    LocationEntryBuilder,
    ZoomPolicyService,
)

if TYPE_CHECKING:
    from location.application.nearby.ports import LocationReader

logger = logging.getLogger(__name__)


class GetNearbyCentersQuery:
    """주변 재활용 센터 조회 Query.

    Workflow:
        1. 줌 정책에 따른 반경/제한 결정 (Service)
        2. 위치 데이터 조회 (Port)
        3. 카테고리 분류 및 필터링 (Service)
        4. DTO 변환 (Service)
    """

    def __init__(self, location_reader: "LocationReader") -> None:
        """Initialize.

        Args:
            location_reader: 위치 데이터 조회 Port
        """
        self._reader = location_reader

    async def execute(self, request: SearchRequest) -> list[LocationEntryDTO]:
        """주변 재활용 센터를 조회합니다.

        Args:
            request: 검색 요청 DTO

        Returns:
            위치 엔트리 DTO 목록
        """
        # 1. 줌 정책에 따른 반경/제한 결정
        effective_radius = request.radius or ZoomPolicyService.radius_from_zoom(request.zoom)
        limit = ZoomPolicyService.limit_from_zoom(request.zoom)

        logger.info(
            "Location search started",
            extra={
                "lat": request.latitude,
                "lon": request.longitude,
                "radius_m": effective_radius,
                "zoom": request.zoom,
            },
        )

        # 2. 위치 데이터 조회 (Port)
        rows = await self._reader.find_within_radius(
            latitude=request.latitude,
            longitude=request.longitude,
            radius_km=effective_radius / 1000,
            limit=limit,
        )

        # 3. 카테고리 분류 및 필터링, 4. DTO 변환
        entries: list[LocationEntryDTO] = []
        for site, distance in rows:
            metadata = site.metadata or {}
            store_category, pickup_categories = CategoryClassifierService.classify(site, metadata)

            # 필터링
            if request.store_filter and store_category not in request.store_filter:
                continue
            if request.pickup_filter:
                entry_pickups = set(pickup_categories or [])
                if not entry_pickups & request.pickup_filter:
                    continue

            # DTO 변환
            entry = LocationEntryBuilder.build(
                site=site,
                distance_km=distance,
                metadata=metadata,
                store_category=store_category,
                pickup_categories=pickup_categories,
            )
            entries.append(entry)

        logger.info("Location search completed", extra={"results_count": len(entries)})
        return entries
