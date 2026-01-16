"""Location Client Port - Location API 호출 추상화.

순수 API 호출만 담당.
비즈니스 로직(컨텍스트 변환)은 LocationService에서 수행.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class LocationDTO:
    """위치 정보 DTO.

    Application Layer에서 사용하는 불변 데이터 객체.
    """

    id: int
    name: str
    road_address: str | None
    latitude: float | None
    longitude: float | None
    distance_km: float
    distance_text: str | None
    store_category: str
    pickup_categories: list[str]
    is_open: bool | None
    phone: str | None


class LocationClientPort(ABC):
    """Location API 클라이언트 Port.

    순수 API 호출만 담당.
    Infrastructure Layer에서 구현 (gRPC 또는 HTTP).
    """

    @abstractmethod
    async def search_recycling_centers(
        self,
        lat: float,
        lon: float,
        radius: int | None = None,
        limit: int = 10,
    ) -> list[LocationDTO]:
        """주변 재활용 센터 검색."""
        pass

    @abstractmethod
    async def search_zerowaste_shops(
        self,
        lat: float,
        lon: float,
        radius: int = 5000,
        limit: int = 10,
    ) -> list[LocationDTO]:
        """주변 제로웨이스트샵 검색."""
        pass
