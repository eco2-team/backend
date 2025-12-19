from fastapi import APIRouter, Depends, HTTPException, Query

from domains.location.domain.value_objects import PickupCategory, StoreCategory
from domains.location.schemas.location import LocationEntry
from domains.location.security import get_current_user, UserInfo
from domains.location.services.location import LocationService

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
        description="Kakao map zoom level (1=street, 14=world). Used when radius omitted.",
    ),
    store_category: str = Query(
        "all",
        description="Comma-separated StoreCategory values. Use 'all' (default) for no filtering.",
    ),
    pickup_category: str = Query(
        "all",
        description="Comma-separated PickupCategory values. Use 'all' (default) for no filtering.",
    ),
    _: UserInfo = Depends(get_current_user),
    service: LocationService = Depends(),
):
    store_filter = _parse_store_category_param(store_category)
    pickup_filter = _parse_pickup_category_param(pickup_category)
    return await service.nearby_centers(
        lat=lat,
        lon=lon,
        radius=radius,
        zoom=zoom,
        store_filter=store_filter,
        pickup_filter=pickup_filter,
    )


def _parse_store_category_param(raw: str) -> set[StoreCategory] | None:
    if not raw or raw.lower() == "all":
        return None
    categories: set[StoreCategory] = set()
    for token in raw.split(","):
        value = token.strip()
        if not value:
            continue
        try:
            categories.add(StoreCategory(value))
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid store_category '{value}'. Allowed values: {[c.value for c in StoreCategory]} or 'all'.",
            ) from exc
    return categories or None


def _parse_pickup_category_param(raw: str) -> set[PickupCategory] | None:
    if not raw or raw.lower() == "all":
        return None
    categories: set[PickupCategory] = set()
    for token in raw.split(","):
        value = token.strip()
        if not value:
            continue
        try:
            categories.add(PickupCategory(value))
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid pickup_category '{value}'. Allowed values: {[c.value for c in PickupCategory]} or 'all'.",
            ) from exc
    return categories or None
