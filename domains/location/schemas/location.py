from typing import Optional

from pydantic import BaseModel


class LocationEntry(BaseModel):
    id: int
    name: str
    source: str
    road_address: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    distance_km: Optional[float] = None
    distance_text: Optional[str] = None
    store_category: str
    pickup_categories: list[str]
    is_holiday: Optional[bool] = None
    is_open: Optional[bool] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    phone: Optional[str] = None


class GeoResponse(BaseModel):
    address: str
    latitude: float
    longitude: float


class CoordinatesPayload(BaseModel):
    latitude: float
    longitude: float
