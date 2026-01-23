"""Kakao Local API Port.

Kakao Local API와의 통신을 위한 포트 인터페이스.
- 키워드 검색 (geocoding, place search)
- 카테고리 검색
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class KakaoPlaceDTO:
    """카카오 장소 DTO."""

    id: str
    place_name: str
    category_name: str
    category_group_code: str
    category_group_name: str
    phone: str | None
    address_name: str
    road_address_name: str | None
    x: str  # longitude
    y: str  # latitude
    place_url: str
    distance: str | None = None

    @property
    def latitude(self) -> float:
        return float(self.y)

    @property
    def longitude(self) -> float:
        return float(self.x)

    @property
    def distance_meters(self) -> int | None:
        if self.distance:
            try:
                return int(self.distance)
            except ValueError:
                return None
        return None

    @property
    def distance_text(self) -> str | None:
        meters = self.distance_meters
        if meters is None:
            return None
        if meters >= 1000:
            return f"{meters / 1000:.1f}km"
        return f"{meters}m"


@dataclass(frozen=True)
class KakaoSearchMeta:
    """카카오 검색 메타 정보."""

    total_count: int = 0
    pageable_count: int = 0
    is_end: bool = True
    same_name: dict[str, Any] | None = None


@dataclass
class KakaoSearchResponse:
    """카카오 검색 응답."""

    places: list[KakaoPlaceDTO] = field(default_factory=list)
    meta: KakaoSearchMeta | None = None
    query: str = ""


class KakaoLocalClientPort(ABC):
    """카카오 로컬 API 포트."""

    @abstractmethod
    async def search_keyword(
        self,
        query: str,
        x: float | None = None,
        y: float | None = None,
        radius: int = 5000,
        page: int = 1,
        size: int = 15,
        sort: str = "accuracy",
    ) -> KakaoSearchResponse:
        """키워드 장소 검색."""
        ...

    @abstractmethod
    async def close(self) -> None:
        """리소스 정리."""
        ...
