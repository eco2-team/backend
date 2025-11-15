from typing import Optional

from pydantic import BaseModel


class Coordinates(BaseModel):
    latitude: float
    longitude: float


class LocationEntry(BaseModel):
    id: int
    name: str
    type: str
    address: str
    coordinates: Coordinates
    distance_km: Optional[float] = None


class GeoResponse(BaseModel):
    address: str
    coordinates: Coordinates
