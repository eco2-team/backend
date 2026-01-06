"""Location Controller."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from location.application.nearby import GetNearbyCentersQuery, SearchRequest
from location.domain.enums import PickupCategory, StoreCategory
from location.presentation.http.schemas import LocationEntry
from location.setup.dependencies import get_nearby_centers_query

router = APIRouter(prefix="/locations", tags=["locations"])


@router.get("/centers", response_model=list[LocationEntry], summary="Find recycling centers")
async def centers(
    query: Annotated[GetNearbyCentersQuery, Depends(get_nearby_centers_query)],
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
) -> list[LocationEntry]:
    """주변 재활용 센터를 조회합니다."""
    store_filter = _parse_store_category_param(store_category)
    pickup_filter = _parse_pickup_category_param(pickup_category)

    request = SearchRequest(
        latitude=lat,
        longitude=lon,
        radius=radius,
        zoom=zoom,
        store_filter=store_filter,
        pickup_filter=pickup_filter,
    )

    entries = await query.execute(request)

    return [
        LocationEntry(
            id=e.id,
            name=e.name,
            source=e.source,
            road_address=e.road_address,
            latitude=e.latitude,
            longitude=e.longitude,
            distance_km=e.distance_km,
            distance_text=e.distance_text,
            store_category=e.store_category,
            pickup_categories=e.pickup_categories,
            is_holiday=e.is_holiday,
            is_open=e.is_open,
            start_time=e.start_time,
            end_time=e.end_time,
            phone=e.phone,
        )
        for e in entries
    ]


def _parse_store_category_param(raw: str) -> set[StoreCategory] | None:
    """store_category 파라미터를 파싱합니다."""
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
    """pickup_category 파라미터를 파싱합니다."""
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
