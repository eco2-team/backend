"""Location gRPC Client - LocationClientPort 구현체.

Location API의 gRPC 서비스를 호출하는 클라이언트.

왜 gRPC인가? (Direct Call vs Queue-based)
- LangGraph는 asyncio 기반 오케스트레이션
- gRPC는 grpc.aio로 asyncio 네이티브 지원
- Location API는 PostGIS 쿼리 후 빠른 응답 (~100ms)
- HTTP보다 낮은 지연 시간, 작은 페이로드

Clean Architecture:
- Port: LocationClientPort (application/integrations/location/ports)
- Adapter: LocationGrpcClient (이 파일)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import grpc

from chat_worker.application.ports.location_client import (
    LocationClientPort,
    LocationDTO,
)
from chat_worker.infrastructure.integrations.location.proto import (
    location_pb2,
    location_pb2_grpc,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# gRPC 타임아웃 (초) - 서비스 SLA 기반
# Location API는 PostGIS 쿼리로 ~100ms 응답, 3초면 충분
DEFAULT_GRPC_TIMEOUT = 3.0


class LocationGrpcClient(LocationClientPort):
    """Location gRPC 클라이언트.

    순수 API 호출만 담당합니다.
    비즈니스 로직은 LocationService에서 수행.

    사용 예:
        client = LocationGrpcClient()
        centers = await client.search_recycling_centers(
            lat=37.5665, lon=126.9780, radius=5000
        )
        context = LocationService.to_answer_context(centers)
    """

    def __init__(
        self,
        host: str = "location-api",
        port: int = 50051,
    ):
        """Initialize.

        Args:
            host: Location API gRPC host
            port: Location API gRPC port
        """
        self._address = f"{host}:{port}"
        self._channel: grpc.aio.Channel | None = None
        self._stub: location_pb2_grpc.LocationServiceStub | None = None

    async def _get_stub(self) -> location_pb2_grpc.LocationServiceStub:
        """Lazy connection - 첫 호출 시 연결."""
        if self._channel is None:
            self._channel = grpc.aio.insecure_channel(self._address)
            self._stub = location_pb2_grpc.LocationServiceStub(self._channel)
            logger.info(
                "Location gRPC channel created",
                extra={"address": self._address},
            )
        return self._stub

    async def search_recycling_centers(
        self,
        lat: float,
        lon: float,
        radius: int | None = None,
        limit: int = 10,
    ) -> list[LocationDTO]:
        """주변 재활용 센터 검색.

        gRPC로 Location API의 SearchNearby 호출.

        Args:
            lat: 위도
            lon: 경도
            radius: 검색 반경 (미터, 기본 5000m)
            limit: 최대 반환 개수 (기본 10)

        Returns:
            재활용 센터 목록
        """
        stub = await self._get_stub()

        request = location_pb2.SearchNearbyRequest(
            latitude=lat,
            longitude=lon,
            radius=radius or 0,  # 0이면 서버 기본값 사용
            limit=limit,
            store_category="all",
            pickup_category="all",
        )

        try:
            response = await stub.SearchNearby(request, timeout=DEFAULT_GRPC_TIMEOUT)

            logger.info(
                "Location SearchNearby completed",
                extra={
                    "lat": lat,
                    "lon": lon,
                    "count": len(response.entries),
                },
            )

            return [
                LocationDTO(
                    id=e.id,
                    name=e.name,
                    road_address=e.road_address or None,
                    latitude=e.latitude,
                    longitude=e.longitude,
                    distance_km=e.distance_km,
                    distance_text=e.distance_text or None,
                    store_category=e.store_category,
                    pickup_categories=list(e.pickup_categories),
                    is_open=e.is_open,
                    phone=e.phone or None,
                )
                for e in response.entries
            ]

        except grpc.aio.AioRpcError as e:
            logger.error(
                "Location gRPC error",
                extra={
                    "lat": lat,
                    "lon": lon,
                    "code": e.code().name,
                    "details": e.details(),
                },
            )
            return []

    async def search_zerowaste_shops(
        self,
        lat: float,
        lon: float,
        radius: int = 5000,
        limit: int = 10,
    ) -> list[LocationDTO]:
        """주변 제로웨이스트샵 검색.

        Note: 현재는 search_recycling_centers와 동일한 gRPC 호출 사용.
        store_category로 필터링하면 됨.
        """
        # 재활용 센터와 동일한 API 사용 (category 필터는 서버에서 처리)
        return await self.search_recycling_centers(lat, lon, radius, limit)

    async def close(self) -> None:
        """연결 종료."""
        if self._channel:
            await self._channel.close()
            self._channel = None
            self._stub = None
            logger.info("Location gRPC channel closed")
