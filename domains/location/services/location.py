import re
from datetime import datetime
from typing import Any, Optional
from zoneinfo import ZoneInfo

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from domains.location.clients.redis_cache import RedisCache
from domains.location.core.config import get_settings
from domains.location.database.session import get_db_session
from domains.location.domain.entities import NormalizedSite
from domains.location.domain.value_objects import (
    Coordinates as DomainCoordinates,
    PickupCategory,
    StoreCategory,
)
from domains.location.repositories.normalized_site_repository import NormalizedLocationRepository
from domains.location.schemas.location import (
    Coordinates,
    GeoResponse,
    LocationEntry,
    OperatingHours,
)
from domains.location.services.category_classifier import classify_categories
from domains.location.services.zoom_policy import limit_from_zoom, radius_from_zoom


class LocationService:
    PLACEHOLDER_MARKERS = {"PLACE", "PHONE", "ADDRESS"}
    WEEKDAY_LABELS = (
        ("mon_sals_hr_expln_cn", "월"),
        ("tues_sals_hr_expln_cn", "화"),
        ("wed_sals_hr_expln_cn", "수"),
        ("thur_sals_hr_expln_cn", "목"),
        ("fri_sals_hr_expln_cn", "금"),
        ("sat_sals_hr_expln_cn", "토"),
        ("sun_sals_hr_expln_cn", "일"),
    )
    TZ = ZoneInfo("Asia/Seoul")

    def __init__(self, session: AsyncSession = Depends(get_db_session)):
        self.repo = NormalizedLocationRepository(session)
        self.settings = get_settings()

    async def nearby_centers(
        self,
        lat: float,
        lon: float,
        radius: int | None,
        zoom: int | None,
        store_filter: set[StoreCategory] | None,
        pickup_filter: set[PickupCategory] | None,
    ) -> list[LocationEntry]:
        effective_radius = radius or radius_from_zoom(zoom)
        limit = limit_from_zoom(zoom)
        rows = await self.repo.find_within_radius(
            latitude=lat,
            longitude=lon,
            radius_km=effective_radius / 1000,
            limit=limit,
        )
        entries: list[LocationEntry] = []
        for site, distance in rows:
            metadata = site.metadata or {}
            store_category, pickup_categories = classify_categories(site, metadata=metadata)

            if store_filter and store_category not in store_filter:
                continue
            if pickup_filter:
                entry_pickups = set(pickup_categories or [])
                if not entry_pickups & pickup_filter:
                    continue

            entries.append(
                self._to_entry(
                    site=site,
                    distance_km=distance,
                    metadata=metadata,
                )
            )
        return entries

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
    def _to_entry(
        site: NormalizedSite, distance_km: float, metadata: dict[str, Any]
    ) -> LocationEntry:
        name = LocationService._first_non_empty(
            metadata.get("display1"),
            site.positn_nm,
            metadata.get("display2"),
            site.positn_lotno_addr,
            site.positn_rdnm_addr,
            site.positn_intdc_cn,
            fallback="Zero Waste Spot",
        )
        road_address = LocationService._derive_road_address(site, metadata)
        coordinates = site.coordinates() or DomainCoordinates(latitude=0.0, longitude=0.0)
        operating_hours = LocationService._derive_operating_hours(site)
        phone = LocationService._derive_phone(site, metadata)
        collection_items = LocationService._derive_collection_items(site, metadata)

        entry = LocationEntry(
            id=int(site.id),
            name=name,
            source=site.source,
            road_address=LocationService._sanitize_optional_text(road_address, source=site.source),
            coordinates=Coordinates(latitude=coordinates.latitude, longitude=coordinates.longitude),
            distance_km=distance_km,
            distance_text=LocationService._format_distance(distance_km),
            operating_hours=operating_hours,
            phone=phone,
            collection_items=collection_items,
        )
        return entry

    @staticmethod
    def _first_non_empty(*values: Any, fallback: str) -> str:
        for value in values:
            if isinstance(value, str) and value:
                return value
        return fallback

    @staticmethod
    def _format_distance(distance_km: float | None) -> Optional[str]:
        if distance_km is None:
            return None
        meters = distance_km * 1000
        if meters < 1000:
            return f"{int(meters)}m"
        return f"{distance_km:.1f}km"

    @staticmethod
    def _derive_operating_hours(site: NormalizedSite) -> Optional[OperatingHours]:
        if site.source == "zerowaste":
            # Zero-waste dataset rarely carries structured hours; avoid leaking memo text.
            return None

        today = datetime.now(LocationService.TZ)
        attr, label = LocationService.WEEKDAY_LABELS[today.weekday()]
        day_value = LocationService._sanitize_optional_text(
            getattr(site, attr, None), source=site.source
        )

        if not day_value:
            return None

        if "휴무" in day_value:
            start_display, end_display = LocationService._extract_time_range(day_value)
            return OperatingHours(
                status="closed",
                start=start_display or day_value,
                end=end_display,
            )

        start_str, end_str = LocationService._extract_time_range(day_value)
        start_display = start_str or day_value
        end_display = end_str

        if start_str and end_str:
            start_dt = LocationService._to_today_datetime(start_str)
            end_dt = LocationService._to_today_datetime(end_str)
            if start_dt and end_dt:
                now = datetime.now(LocationService.TZ)
                if start_dt <= now <= end_dt:
                    return OperatingHours(status="open", start=start_display, end=end_display)
        return OperatingHours(status="closed", start=start_display, end=end_display)

    @staticmethod
    def _derive_phone(site: NormalizedSite, metadata: dict[str, Any]) -> Optional[str]:
        raw = LocationService._first_non_empty(
            metadata.get("bscTelnoCn"),
            metadata.get("rprsTelnoCn"),
            metadata.get("telnoExpln"),
            metadata.get("indivTelnoCn"),
            fallback="",
        )
        return LocationService._normalize_phone(raw, source=site.source)

    @staticmethod
    def _derive_road_address(site: NormalizedSite, metadata: dict[str, Any]) -> str:
        return LocationService._first_non_empty(
            site.positn_rdnm_addr,
            metadata.get("display2"),
            site.positn_lotno_addr,
            metadata.get("display1"),
            site.positn_pstn_add_expln,
            fallback="",
        )

    @staticmethod
    def _derive_collection_items(
        site: NormalizedSite, metadata: dict[str, Any]
    ) -> Optional[list[str]]:
        raw = metadata.get("clctItemCn") or metadata.get("clct_item_cn") or site.clct_item_cn
        if not raw:
            return None

        if isinstance(raw, (list, tuple, set)):
            tokens = list(raw)
        else:
            text = str(raw).replace("\r", "\n")
            tokens = re.split(r"[\n,]+", text)

        cleaned: list[str] = []
        for token in tokens:
            normalized = LocationService._sanitize_optional_text(token, source=site.source)
            if normalized:
                cleaned.append(normalized)
        return cleaned or None

    @staticmethod
    def _sanitize_optional_text(value: Optional[str], *, source: str | None) -> Optional[str]:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            return None
        if source == "zerowaste" and normalized.upper() in LocationService.PLACEHOLDER_MARKERS:
            return None
        return normalized

    @staticmethod
    def _normalize_phone(value: Optional[str], *, source: str | None) -> Optional[str]:
        sanitized = LocationService._sanitize_optional_text(value, source=source)
        if not sanitized:
            return None
        digit_groups = re.findall(r"\d+", sanitized)
        if not digit_groups:
            return None
        collapsed = "".join(digit_groups)
        if len(digit_groups) == 1 and len(collapsed) == 11:
            return f"{collapsed[:3]}-{collapsed[3:7]}-{collapsed[7:]}"
        if len(digit_groups) >= 3:
            return "-".join(digit_groups[:3])
        return "-".join(digit_groups) or None

    @staticmethod
    def _extract_time_range(value: str) -> tuple[Optional[str], Optional[str]]:
        match = re.search(r"(\d{1,2}:\d{2})\s*~\s*(\d{1,2}:\d{2})", value)
        if match:
            return match.group(1), match.group(2)
        numbers = re.findall(r"\d{1,2}:\d{2}", value)
        if len(numbers) >= 2:
            return numbers[0], numbers[1]
        if "~" in value:
            parts = [part.strip() for part in value.split("~", 1)]
            if len(parts) == 2:
                return parts[0] or None, parts[1] or None
        return None, None

    @staticmethod
    def _to_today_datetime(value: str) -> Optional[datetime]:
        try:
            parsed = datetime.strptime(value, "%H:%M").time()
        except ValueError:
            return None
        today = datetime.now(LocationService.TZ)
        return datetime.combine(today.date(), parsed, tzinfo=LocationService.TZ)
