"""Location Entry Builder Service.

NormalizedSite 엔티티를 LocationEntryDTO로 변환합니다.
Port 의존성이 없는 순수 로직입니다.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from zoneinfo import ZoneInfo

from location.application.nearby.dto import LocationEntryDTO
from location.domain.entities import NormalizedSite
from location.domain.enums import PickupCategory, StoreCategory


class LocationEntryBuilder:
    """위치 엔트리 빌더 서비스."""

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

    @classmethod
    def build(
        cls,
        site: NormalizedSite,
        distance_km: float,
        metadata: dict[str, Any],
        store_category: StoreCategory,
        pickup_categories: list[PickupCategory],
    ) -> LocationEntryDTO:
        """NormalizedSite를 LocationEntryDTO로 변환합니다."""
        name = cls._first_non_empty(
            metadata.get("display1"),
            site.positn_nm,
            metadata.get("display2"),
            site.positn_lotno_addr,
            site.positn_rdnm_addr,
            site.positn_intdc_cn,
            fallback="Zero Waste Spot",
        )
        road_address = cls._derive_road_address(site, metadata)
        coordinates = site.coordinates()
        operating_hours = cls._derive_operating_hours(site)
        phone = cls._derive_phone(site, metadata)

        return LocationEntryDTO(
            id=int(site.id),
            name=name,
            source=site.source,
            road_address=cls._sanitize_optional_text(road_address, source=site.source),
            latitude=coordinates.latitude if coordinates else None,
            longitude=coordinates.longitude if coordinates else None,
            distance_km=distance_km,
            distance_text=cls._format_distance(distance_km),
            store_category=store_category.value,
            pickup_categories=[c.value for c in pickup_categories]
            or [PickupCategory.GENERAL.value],
            is_holiday=operating_hours.get("is_holiday") if operating_hours else None,
            is_open=operating_hours.get("is_open") if operating_hours else None,
            start_time=operating_hours.get("start_time") if operating_hours else None,
            end_time=operating_hours.get("end_time") if operating_hours else None,
            phone=phone,
        )

    @staticmethod
    def _first_non_empty(*values: Any, fallback: str) -> str:
        for value in values:
            if isinstance(value, str) and value:
                return value
        return fallback

    @staticmethod
    def _format_distance(distance_km: float | None) -> str | None:
        if distance_km is None:
            return None
        meters = distance_km * 1000
        if meters < 1000:
            return f"{int(meters)}m"
        return f"{distance_km:.1f}km"

    @classmethod
    def _derive_operating_hours(cls, site: NormalizedSite) -> dict[str, Any] | None:
        payload: dict[str, Any] = {
            "is_holiday": None,
            "is_open": False,
            "start_time": None,
            "end_time": None,
        }

        if site.source == "zerowaste":
            return payload

        today = datetime.now(cls.TZ)
        attr, _ = cls.WEEKDAY_LABELS[today.weekday()]
        day_value = cls._sanitize_optional_text(getattr(site, attr, None), source=site.source)

        if not day_value:
            return payload

        if "휴무" in day_value:
            payload["is_holiday"] = True
            return payload

        start_str, end_str = cls._extract_time_range(day_value)
        start_display = start_str or day_value
        end_display = end_str

        payload["is_holiday"] = False
        payload["start_time"] = start_display
        payload["end_time"] = end_display

        if start_str and end_str:
            start_dt = cls._to_today_datetime(start_str)
            end_dt = cls._to_today_datetime(end_str)
            if start_dt and end_dt:
                now = datetime.now(cls.TZ)
                if start_dt <= now <= end_dt:
                    payload["is_open"] = True

        return payload

    @classmethod
    def _derive_phone(cls, site: NormalizedSite, metadata: dict[str, Any]) -> str | None:
        raw = cls._first_non_empty(
            metadata.get("bscTelnoCn"),
            metadata.get("rprsTelnoCn"),
            metadata.get("telnoExpln"),
            metadata.get("indivTelnoCn"),
            fallback="",
        )
        return cls._normalize_phone(raw, source=site.source)

    @classmethod
    def _derive_road_address(cls, site: NormalizedSite, metadata: dict[str, Any]) -> str:
        return cls._first_non_empty(
            site.positn_rdnm_addr,
            metadata.get("display2"),
            site.positn_lotno_addr,
            metadata.get("display1"),
            site.positn_pstn_add_expln,
            fallback="",
        )

    @classmethod
    def _sanitize_optional_text(cls, value: str | None, *, source: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            return None
        if source == "zerowaste" and normalized.upper() in cls.PLACEHOLDER_MARKERS:
            return None
        return normalized

    @classmethod
    def _normalize_phone(cls, value: str | None, *, source: str | None) -> str | None:
        sanitized = cls._sanitize_optional_text(value, source=source)
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
    def _extract_time_range(value: str) -> tuple[str | None, str | None]:
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

    @classmethod
    def _to_today_datetime(cls, value: str) -> datetime | None:
        try:
            parsed = datetime.strptime(value, "%H:%M").time()
        except ValueError:
            return None
        today = datetime.now(cls.TZ)
        return datetime.combine(today.date(), parsed, tzinfo=cls.TZ)
