from fastapi import APIRouter, Depends, Query

from domains.location.schemas.location import Coordinates, GeoResponse, LocationEntry
from domains.location.security import access_token_dependency
from domains.location.services.location import LocationService
from domains._shared.security import TokenPayload

router = APIRouter(prefix="/locations", tags=["locations"])


@router.get("/centers", response_model=list[LocationEntry], summary="Find recycling centers")
async def centers(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    radius: int | None = Query(
        None,
        ge=100,
        le=50000,
        description="Optional radius in meters (overrides auto radius from zoom)",
    ),
    zoom: int | None = Query(
        None,
        ge=1,
        le=20,
        description="Kakao map zoom level (1=world, 14=street). Used when radius omitted.",
    ),
    _: TokenPayload = Depends(access_token_dependency),
    service: LocationService = Depends(),
):
    return await service.nearby_centers(lat=lat, lon=lon, radius=radius, zoom=zoom)


@router.post("/geocode", response_model=GeoResponse, summary="Address to coordinates")
async def geocode(
    address: str,
    _: TokenPayload = Depends(access_token_dependency),
    service: LocationService = Depends(),
):
    return await service.geocode(address)


@router.post("/reverse-geocode", response_model=GeoResponse, summary="Coordinates to address")
async def reverse_geocode(
    payload: Coordinates,
    _: TokenPayload = Depends(access_token_dependency),
    service: LocationService = Depends(),
):
    return await service.reverse_geocode(payload)