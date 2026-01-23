"""Location HTTP Schemas."""

from __future__ import annotations

from pydantic import BaseModel


class LocationEntry(BaseModel):
    """위치 정보 응답 스키마."""

    id: int
    name: str
    source: str
    road_address: str | None
    latitude: float | None
    longitude: float | None
    distance_km: float
    distance_text: str | None
    store_category: str
    pickup_categories: list[str]
    is_holiday: bool | None
    is_open: bool | None
    start_time: str | None
    end_time: str | None
    phone: str | None
    place_url: str | None = None
    kakao_place_id: str | None = None

    model_config = {"from_attributes": True}


class SuggestEntry(BaseModel):
    """자동완성 제안 스키마."""

    place_name: str
    address: str | None
    latitude: float
    longitude: float
    place_url: str | None = None


class LocationDetail(BaseModel):
    """장소 상세 응답 스키마."""

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
