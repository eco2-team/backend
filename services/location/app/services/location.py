from app.schemas.location import Coordinates, GeoResponse, LocationEntry


class LocationService:
    async def nearby_bins(self, lat: float, lon: float, radius: int) -> list[LocationEntry]:
        return [
            LocationEntry(
                id=1,
                name="Community Recycling Bin",
                type="bin",
                address="Gangnam-gu, Seoul",
                coordinates=Coordinates(latitude=lat + 0.001, longitude=lon + 0.001),
                distance_km=0.3,
            )
        ]

    async def nearby_centers(self, lat: float, lon: float, radius: int) -> list[LocationEntry]:
        return [
            LocationEntry(
                id=11,
                name="Seoul Recycling Center",
                type="center",
                address="Seoul Metropolitan",
                coordinates=Coordinates(latitude=lat + 0.01, longitude=lon + 0.01),
                distance_km=2.1,
            )
        ]

    async def geocode(self, address: str) -> GeoResponse:
        return GeoResponse(
            address=address,
            coordinates=Coordinates(latitude=37.5665, longitude=126.9780),
        )

    async def reverse_geocode(self, coordinates: Coordinates) -> GeoResponse:
        return GeoResponse(address="Seoul City Hall", coordinates=coordinates)

    async def metrics(self) -> dict:
        return {
            "bins_indexed": 102,
            "centers_indexed": 12,
            "geocode_requests_24h": 320,
        }
