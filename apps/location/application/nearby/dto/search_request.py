"""Search Request DTO."""

from __future__ import annotations

from dataclasses import dataclass

from location.domain.enums import PickupCategory, StoreCategory


@dataclass
class SearchRequest:
    """위치 검색 요청 DTO."""

    latitude: float
    longitude: float
    radius: int | None = None
    zoom: int | None = None
    store_filter: set[StoreCategory] | None = None
    pickup_filter: set[PickupCategory] | None = None
