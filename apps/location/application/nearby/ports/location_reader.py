"""Location Reader Port."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Sequence

from location.domain.entities import NormalizedSite


class LocationReader(ABC):
    """위치 데이터 조회 포트.

    Infrastructure Layer에서 구현합니다.
    """

    @abstractmethod
    async def find_within_radius(
        self,
        latitude: float,
        longitude: float,
        radius_km: float,
        limit: int,
    ) -> Sequence[tuple[NormalizedSite, float]]:
        """주어진 좌표에서 반경 내 위치를 조회합니다.

        Args:
            latitude: 위도
            longitude: 경도
            radius_km: 반경 (km)
            limit: 최대 결과 수

        Returns:
            (NormalizedSite, 거리_km) 튜플 목록
        """
        ...

    @abstractmethod
    async def find_by_id(self, site_id: int) -> NormalizedSite | None:
        """ID로 사이트를 조회합니다.

        Args:
            site_id: 사이트 ID

        Returns:
            NormalizedSite 또는 None (미발견 시)
        """
        ...

    @abstractmethod
    async def count_sites(self) -> int:
        """전체 사이트 수를 반환합니다."""
        ...
