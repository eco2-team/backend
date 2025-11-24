from enum import Enum
from typing import Optional

from pydantic import BaseModel


class Coordinates(BaseModel):
    latitude: float
    longitude: float


class LocationCategory(str, Enum):
    REFILL_ZERO = "refill_zero"
    CAFE_BAKERY = "cafe_bakery"
    VEGAN_DINING = "vegan_dining"
    UPCYCLE_RECYCLE = "upcycle_recycle"
    BOOK_WORKSHOP = "book_workshop"
    MARKET_MART = "market_mart"
    LODGING = "lodging"
    GENERAL = "general"
    ADDRESS_ONLY = "address_only"


class LocationEntry(BaseModel):
    id: int
    name: str
    type: str
    category: LocationCategory = LocationCategory.GENERAL
    address: str
    coordinates: Coordinates
    distance_km: Optional[float] = None


class GeoResponse(BaseModel):
    address: str
    coordinates: Coordinates
