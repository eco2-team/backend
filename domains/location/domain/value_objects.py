from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class StoreCategory(str, Enum):
    REFILL_ZERO = "refill_zero"
    CAFE_BAKERY = "cafe_bakery"
    VEGAN_DINING = "vegan_dining"
    UPCYCLE_RECYCLE = "upcycle_recycle"
    BOOK_WORKSHOP = "book_workshop"
    MARKET_MART = "market_mart"
    LODGING = "lodging"
    PUBLIC_DROPBOX = "public_dropbox"
    GENERAL = "general"


class PickupCategory(str, Enum):
    CLEAR_PET = "clear_pet"
    COLORED_PET = "colored_pet"
    CAN = "can"
    PAPER = "paper"
    PLASTIC = "plastic"
    GLASS = "glass"
    TEXTILE = "textile"
    ELECTRONICS = "electronics"
    GENERAL = "general"


@dataclass(frozen=True)
class Coordinates:
    latitude: float
    longitude: float
