"""Location Detail DTO."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class LocationDetailDTO:
    """장소 상세 정보 DTO."""

    id: int
    name: str
    source: str
    road_address: str | None
    lot_address: str | None
    latitude: float | None
    longitude: float | None
    store_category: str
    pickup_categories: list[str]
    phone: str | None
    place_url: str | None = None
    kakao_place_id: str | None = None
    collection_items: str | None = None
    introduction: str | None = None
