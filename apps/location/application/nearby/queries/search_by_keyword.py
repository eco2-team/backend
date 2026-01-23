"""Search By Keyword Query.

키워드 검색 Query. Kakao API + DB 하이브리드 검색.
"""

from __future__ import annotations

import logging
import math
from typing import TYPE_CHECKING

from location.application.nearby.dto import LocationEntryDTO
from location.application.nearby.services import (
    CategoryClassifierService,
    LocationEntryBuilder,
)

if TYPE_CHECKING:
    from location.application.nearby.ports import LocationReader
    from location.application.ports.kakao_local_client import (
        KakaoLocalClientPort,
        KakaoPlaceDTO,
    )

logger = logging.getLogger(__name__)

DEFAULT_SEARCH_RADIUS_KM = 5.0
MAX_DB_RESULTS = 50
MAX_KAKAO_RESULTS = 10


class SearchByKeywordQuery:
    """키워드 기반 하이브리드 검색 Query.

    Workflow:
        1. Kakao API로 키워드 검색 → 좌표 및 장소 목록 획득
        2. 첫 번째 결과의 좌표로 DB spatial query 실행
        3. DB 결과 + Kakao 결과 병합 (중복 제거)
    """

    def __init__(
        self,
        location_reader: "LocationReader",
        kakao_client: "KakaoLocalClientPort",
    ) -> None:
        self._reader = location_reader
        self._kakao = kakao_client

    async def execute(
        self,
        query: str,
        radius: int = 5000,
    ) -> list[LocationEntryDTO]:
        """키워드로 장소를 검색합니다.

        Args:
            query: 검색 키워드 (예: "강남역 재활용센터")
            radius: 검색 반경 (미터)

        Returns:
            LocationEntryDTO 목록 (거리순 정렬)
        """
        logger.info("Keyword search started", extra={"query": query, "radius": radius})

        # 1. Kakao API 키워드 검색
        kakao_response = await self._kakao.search_keyword(
            query=query,
            size=MAX_KAKAO_RESULTS,
            sort="accuracy",
        )

        kakao_places = kakao_response.places
        if not kakao_places:
            logger.info("No Kakao results", extra={"query": query})
            return []

        # 2. 첫 번째 결과의 좌표를 기준으로 DB 검색
        anchor = kakao_places[0]
        anchor_lat = anchor.latitude
        anchor_lon = anchor.longitude

        # 좌표 기반으로 Kakao 재검색 (거리 정보 포함)
        kakao_nearby = await self._kakao.search_keyword(
            query=query,
            x=anchor_lon,
            y=anchor_lat,
            radius=radius,
            size=MAX_KAKAO_RESULTS,
            sort="distance",
        )
        kakao_places = kakao_nearby.places if kakao_nearby.places else kakao_places

        # 3. DB spatial query
        radius_km = radius / 1000.0
        db_rows = await self._reader.find_within_radius(
            latitude=anchor_lat,
            longitude=anchor_lon,
            radius_km=radius_km,
            limit=MAX_DB_RESULTS,
        )

        # 4. DB 결과를 LocationEntryDTO로 변환
        db_entries: list[LocationEntryDTO] = []
        db_coords: list[tuple[float, float]] = []
        for site, distance in db_rows:
            metadata = site.metadata or {}
            store_category, pickup_categories = CategoryClassifierService.classify(site, metadata)
            entry = LocationEntryBuilder.build(
                site=site,
                distance_km=distance,
                metadata=metadata,
                store_category=store_category,
                pickup_categories=pickup_categories,
            )
            db_entries.append(entry)
            if site.positn_pstn_lat and site.positn_pstn_lot:
                db_coords.append((site.positn_pstn_lat, site.positn_pstn_lot))

        # 5. Kakao 결과 중 DB에 없는 장소만 추가 (50m 이내 중복 제거)
        kakao_entries: list[LocationEntryDTO] = []
        kakao_id_counter = -1
        for place in kakao_places:
            if self._is_duplicate(place.latitude, place.longitude, db_coords):
                continue
            kakao_entries.append(
                self._kakao_to_entry(place, anchor_lat, anchor_lon, kakao_id_counter)
            )
            kakao_id_counter -= 1

        # 6. 병합: DB 결과 우선, Kakao 보충
        merged = db_entries + kakao_entries
        merged.sort(key=lambda e: e.distance_km)

        logger.info(
            "Keyword search completed",
            extra={
                "query": query,
                "db_count": len(db_entries),
                "kakao_count": len(kakao_entries),
                "total": len(merged),
            },
        )
        return merged

    @staticmethod
    def _is_duplicate(
        lat: float, lon: float, coords: list[tuple[float, float]], threshold_m: float = 50.0
    ) -> bool:
        """좌표 근접도 기반 중복 판별 (threshold_m 미터 이내)."""
        for db_lat, db_lon in coords:
            dist = _haversine_meters(lat, lon, db_lat, db_lon)
            if dist <= threshold_m:
                return True
        return False

    @staticmethod
    def _kakao_to_entry(
        place: "KakaoPlaceDTO", anchor_lat: float, anchor_lon: float, entry_id: int = -1
    ) -> LocationEntryDTO:
        """Kakao 장소를 LocationEntryDTO로 변환."""
        if place.distance_meters is not None:
            distance_km = place.distance_meters / 1000.0
        else:
            distance_km = (
                _haversine_meters(anchor_lat, anchor_lon, place.latitude, place.longitude) / 1000.0
            )

        return LocationEntryDTO(
            id=entry_id,
            name=place.place_name,
            source="kakao",
            road_address=place.road_address_name or place.address_name,
            latitude=place.latitude,
            longitude=place.longitude,
            distance_km=distance_km,
            distance_text=place.distance_text or _format_distance(distance_km),
            store_category="general",
            pickup_categories=[],
            is_holiday=None,
            is_open=None,
            start_time=None,
            end_time=None,
            phone=place.phone,
            place_url=place.place_url,
            kakao_place_id=place.id,
        )


def _haversine_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """두 좌표 간 거리를 미터로 계산 (Haversine)."""
    r = 6371000.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return r * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _format_distance(distance_km: float) -> str:
    if distance_km >= 1.0:
        return f"{distance_km:.1f}km"
    return f"{int(distance_km * 1000)}m"
