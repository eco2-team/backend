"""Location gRPC Servicer.

gRPC 요청을 처리하고 Clean Architecture의 Application 계층을 호출합니다.

RPC Methods:
- SearchNearby: 주변 재활용 센터 검색 (Chat Worker용)
"""

import logging
from typing import TYPE_CHECKING

import grpc

from location.application.nearby import GetNearbyCentersQuery, SearchRequest
from location.domain.enums import PickupCategory, StoreCategory
from location.proto import location_pb2, location_pb2_grpc

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class LocationServicer(location_pb2_grpc.LocationServiceServicer):
    """Location gRPC Servicer.

    Clean Architecture의 Application 계층과 연결됩니다.
    """

    def __init__(self, nearby_query: GetNearbyCentersQuery) -> None:
        """Initialize.

        Args:
            nearby_query: 주변 센터 검색 Query
        """
        self._nearby_query = nearby_query

    async def SearchNearby(
        self,
        request: location_pb2.SearchNearbyRequest,
        context: grpc.aio.ServicerContext,
    ) -> location_pb2.SearchNearbyResponse:
        """주변 재활용 센터를 검색합니다.

        Chat Worker의 Location Subagent에서 호출됩니다.
        """
        try:
            # 1. 카테고리 파싱
            store_filter = self._parse_store_category(request.store_category)
            pickup_filter = self._parse_pickup_category(request.pickup_category)

            # 2. Application Query 실행
            search_request = SearchRequest(
                latitude=request.latitude,
                longitude=request.longitude,
                radius=request.radius if request.radius > 0 else None,
                zoom=None,
                store_filter=store_filter,
                pickup_filter=pickup_filter,
            )

            entries = await self._nearby_query.execute(search_request)

            # 3. limit 적용
            limit = request.limit if request.limit > 0 else 10
            entries = entries[:limit]

            # 4. Protobuf 응답 생성
            response_entries = [
                location_pb2.LocationEntry(
                    id=e.id,
                    name=e.name,
                    road_address=e.road_address or "",
                    latitude=e.latitude or 0,
                    longitude=e.longitude or 0,
                    distance_km=e.distance_km,
                    distance_text=e.distance_text or "",
                    store_category=e.store_category,
                    pickup_categories=e.pickup_categories,
                    is_open=e.is_open or False,
                    phone=e.phone or "",
                )
                for e in entries
            ]

            logger.info(
                "SearchNearby completed",
                extra={
                    "lat": request.latitude,
                    "lon": request.longitude,
                    "count": len(response_entries),
                },
            )

            return location_pb2.SearchNearbyResponse(
                entries=response_entries,
                total_count=len(response_entries),
            )

        except Exception:
            logger.exception(
                "Internal error in SearchNearby",
                extra={
                    "lat": request.latitude,
                    "lon": request.longitude,
                },
            )
            await context.abort(grpc.StatusCode.INTERNAL, "Internal server error")

    def _parse_store_category(self, raw: str) -> set[StoreCategory] | None:
        """store_category 파라미터를 파싱합니다."""
        if not raw or raw.lower() == "all":
            return None
        try:
            return {StoreCategory(v.strip()) for v in raw.split(",")}
        except ValueError:
            return None

    def _parse_pickup_category(self, raw: str) -> set[PickupCategory] | None:
        """pickup_category 파라미터를 파싱합니다."""
        if not raw or raw.lower() == "all":
            return None
        try:
            return {PickupCategory(v.strip()) for v in raw.split(",")}
        except ValueError:
            return None
