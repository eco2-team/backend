from fastapi import APIRouter, Depends, Query

from app.schemas.location import Coordinates, GeoResponse, LocationEntry
from app.services.location import LocationService

router = APIRouter(prefix="/locations", tags=["locations"])


@router.get("/bins", response_model=list[LocationEntry], summary="Find recycling bins nearby")
async def bins(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    radius: int = Query(1000, ge=100, le=10000, description="radius in meters"),
    service: LocationService = Depends(),
):
    return await service.nearby_bins(lat=lat, lon=lon, radius=radius)


@router.get("/centers", response_model=list[LocationEntry], summary="Find recycling centers")
async def centers(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    radius: int = Query(5000, ge=100, le=50000),
    service: LocationService = Depends(),
):
    return await service.nearby_centers(lat=lat, lon=lon, radius=radius)


@router.post("/geocode", response_model=GeoResponse, summary="Address to coordinates")
async def geocode(address: str, service: LocationService = Depends()):
    return await service.geocode(address)


@router.post("/reverse-geocode", response_model=GeoResponse, summary="Coordinates to address")
async def reverse_geocode(payload: Coordinates, service: LocationService = Depends()):
    return await service.reverse_geocode(payload)
