"""Location Controller."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from location.application.common.exceptions.validation import (
    InvalidPickupCategoryError,
    InvalidStoreCategoryError,
    KakaoApiUnavailableError,
)
from location.application.nearby import GetNearbyCentersQuery, SearchRequest
from location.application.nearby.queries.search_by_keyword import SearchByKeywordQuery
from location.domain.enums import PickupCategory, StoreCategory
from location.domain.exceptions.location import LocationNotFoundError
from location.presentation.http.schemas import LocationDetail, LocationEntry, SuggestEntry
from location.setup.dependencies import (
    get_center_detail_query,
    get_nearby_centers_query,
    get_search_by_keyword_query,
    get_suggest_places_query,
)

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


@router.get("/search", response_model=list[LocationEntry], summary="Search locations by keyword")
async def search(
    search_query: Annotated[SearchByKeywordQuery | None, Depends(get_search_by_keyword_query)],
    q: str = Query(..., min_length=1, max_length=100, description="검색 키워드"),
    radius: int = Query(5000, ge=100, le=20000, description="검색 반경 (미터)"),
) -> list[LocationEntry]:
    """키워드로 장소를 검색합니다 (Kakao API + DB 하이브리드)."""
    if search_query is None:
        raise KakaoApiUnavailableError()

    entries = await search_query.execute(query=q, radius=radius)

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
            place_url=e.place_url,
            kakao_place_id=e.kakao_place_id,
        )
        for e in entries
    ]


@router.get(
    "/suggest", response_model=list[SuggestEntry], summary="Suggest places for autocomplete"
)
async def suggest(
    query: str = Query(..., min_length=1, max_length=100, alias="q", description="검색어"),
) -> list[SuggestEntry]:
    """자동완성을 위한 장소 제안을 반환합니다."""
    suggest_query = get_suggest_places_query()
    if suggest_query is None:
        raise KakaoApiUnavailableError()

    places = await suggest_query.execute(query=query)
    return [
        SuggestEntry(
            place_name=p.place_name,
            address=p.address,
            latitude=p.latitude,
            longitude=p.longitude,
            place_url=p.place_url,
        )
        for p in places
    ]


@router.get("/centers/{center_id}", response_model=LocationDetail, summary="Get location detail")
async def center_detail(
    center_id: int,
    detail_query=Depends(get_center_detail_query),
) -> LocationDetail:
    """장소 상세 정보를 조회합니다."""
    result = await detail_query.execute(center_id=center_id)
    if result is None:
        raise LocationNotFoundError()

    return LocationDetail(
        id=result.id,
        name=result.name,
        source=result.source,
        road_address=result.road_address,
        lot_address=result.lot_address,
        latitude=result.latitude,
        longitude=result.longitude,
        store_category=result.store_category,
        pickup_categories=result.pickup_categories,
        phone=result.phone,
        place_url=result.place_url,
        kakao_place_id=result.kakao_place_id,
        collection_items=result.collection_items,
        introduction=result.introduction,
    )


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
        except ValueError:
            raise InvalidStoreCategoryError(value=value, allowed=[c.value for c in StoreCategory])
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
        except ValueError:
            raise InvalidPickupCategoryError(value=value, allowed=[c.value for c in PickupCategory])
    return categories or None
