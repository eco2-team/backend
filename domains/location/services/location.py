from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from domains.location.clients.redis_cache import RedisCache
from domains.location.core.config import get_settings
from domains.location.database.session import get_db_session
from domains.location.models import ZeroWasteSite
from domains.location.repositories.zero_waste_repository import ZeroWasteRepository
from domains.location.schemas.location import (
    Coordinates,
    GeoResponse,
    LocationEntry,
)
from domains.location.services.category_classifier import classify_category
from domains.location.services.zoom_policy import (
    DEFAULT_RADIUS_METERS,
    limit_from_zoom,
    radius_from_zoom,
)

class LocationService:
    def __init__(self, session: AsyncSession = Depends(get_db_session)):
        self.repo = ZeroWasteRepository(session)
        self.settings = get_settings()

    async def nearby_centers(
        self,
        lat: float,
        lon: float,
        radius: int | None,
        zoom: int | None,
    ) -> list[LocationEntry]:
        effective_radius = radius or radius_from_zoom(zoom)
        limit = limit_from_zoom(zoom)
        rows = await self.repo.find_within_radius(
            latitude=lat,
            longitude=lon,
            radius_km=effective_radius / 1000,
            limit=limit,
        )
        return [self._to_entry(site, distance) for site, distance in rows]

    async def geocode(self, address: str) -> GeoResponse:
        # Placeholder: future integration with external geocoding provider
        return GeoResponse(
            address=address,
            coordinates=Coordinates(latitude=37.5665, longitude=126.9780),
        )

    async def reverse_geocode(self, coordinates: Coordinates) -> GeoResponse:
        # Placeholder
        return GeoResponse(address="Seoul City Hall", coordinates=coordinates)

    async def metrics(self) -> dict:
        cache_key = "location:indexed_sites"
        cached = await RedisCache.get(cache_key)
        if cached is not None:
            return {"indexed_sites": int(cached)}

        total = await self.repo.count_sites()
        await RedisCache.set(cache_key, total, self.settings.metrics_cache_ttl_seconds)
        return {
            "indexed_sites": total,
        }

    @staticmethod
    def _to_entry(site: ZeroWasteSite, distance_km: float) -> LocationEntry:
        return LocationEntry(
            id=site.seq,
            name=site.display1 or site.display2 or (site.memo or "Zero Waste Spot"),
            type=site.favorite_type or "PLACE",
            category=classify_category(site),
            address=site.display2 or site.display1 or "",
            coordinates=Coordinates(latitude=site.lat, longitude=site.lon),
            distance_km=distance_km,
        )

