from typing import Optional

from pydantic import BaseModel


class Coordinates(BaseModel):
    latitude: float
    longitude: float


class OperatingHours(BaseModel):
    status: str
    start: Optional[str] = None
    end: Optional[str] = None


class LocationEntry(BaseModel):
    id: int
    name: str
    source: str
    road_address: Optional[str] = None
    coordinates: Coordinates
    distance_km: Optional[float] = None
    distance_text: Optional[str] = None
    operating_hours: Optional[OperatingHours] = None
    phone: Optional[str] = None
    collection_items: Optional[list[str]] = None


class GeoResponse(BaseModel):
    address: str
    coordinates: Coordinates
