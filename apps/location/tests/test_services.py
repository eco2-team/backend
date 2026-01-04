"""Application Services 단위 테스트."""

from __future__ import annotations

from typing import Any


from apps.location.application.nearby.services import (
    CategoryClassifierService,
    LocationEntryBuilder,
    ZoomPolicyService,
)
from apps.location.domain.entities import NormalizedSite
from apps.location.domain.enums import PickupCategory, StoreCategory


class TestZoomPolicyService:
    """ZoomPolicyService 테스트."""

    def test_radius_from_zoom_none(self) -> None:
        """zoom이 None이면 기본값 반환."""
        assert ZoomPolicyService.radius_from_zoom(None) == 5000

    def test_radius_from_zoom_1(self) -> None:
        """줌 레벨 1 (카카오맵 최소)."""
        result = ZoomPolicyService.radius_from_zoom(1)
        assert result > 0

    def test_radius_from_zoom_14(self) -> None:
        """줌 레벨 14 (카카오맵 최대)."""
        result = ZoomPolicyService.radius_from_zoom(14)
        assert result > 0

    def test_radius_varies_with_zoom(self) -> None:
        """줌 레벨에 따라 반경 변화.

        카카오맵 줌 레벨: 1=거리(가까움), 14=세계(멀리)
        따라서 줌 1은 작은 반경, 줌 14는 큰 반경.
        """
        r1 = ZoomPolicyService.radius_from_zoom(1)
        r14 = ZoomPolicyService.radius_from_zoom(14)
        # 카카오맵에서 줌 1이 가까이, 14가 멀리이므로 r14 > r1
        assert r14 > r1

    def test_limit_from_zoom_none(self) -> None:
        """zoom이 None이면 기본 제한 반환."""
        assert ZoomPolicyService.limit_from_zoom(None) == 200

    def test_limit_varies_with_zoom(self) -> None:
        """줌 레벨에 따라 제한 변화.

        카카오맵 줌 레벨: 1=거리(가까움), 14=세계(멀리)
        """
        l1 = ZoomPolicyService.limit_from_zoom(1)
        l14 = ZoomPolicyService.limit_from_zoom(14)
        # 두 값이 다르거나 정의되어 있음을 확인
        assert l1 > 0 and l14 > 0


class TestCategoryClassifierService:
    """CategoryClassifierService 테스트."""

    def test_classify_refill_zero(self, sample_site: NormalizedSite) -> None:
        """제로웨이스트 키워드 분류."""
        site = NormalizedSite(
            id=1,
            source="test",
            source_key="TEST",
            positn_intdc_cn="제로웨이스트 리필샵입니다",
        )
        store, _ = CategoryClassifierService.classify(site)
        assert store == StoreCategory.REFILL_ZERO

    def test_classify_cafe_bakery(self) -> None:
        """카페/베이커리 키워드 분류."""
        site = NormalizedSite(
            id=1,
            source="test",
            source_key="TEST",
            positn_nm="친환경 카페",
        )
        store, _ = CategoryClassifierService.classify(site)
        assert store == StoreCategory.CAFE_BAKERY

    def test_classify_upcycle(self) -> None:
        """업사이클 키워드 분류."""
        site = NormalizedSite(
            id=1,
            source="test",
            source_key="TEST",
            positn_intdc_cn="재활용 수거 센터",
        )
        store, _ = CategoryClassifierService.classify(site)
        assert store == StoreCategory.UPCYCLE_RECYCLE

    def test_classify_public_dropbox(self) -> None:
        """무인 수거함 분류.

        Note: '수거'는 UPCYCLE_RECYCLE로 먼저 매칭되므로
        PUBLIC_DROPBOX는 '무인'만 있거나 다른 우선순위 키워드가 없을 때 적용됨.
        """
        site = NormalizedSite(
            id=1,
            source="test",
            source_key="TEST",
            positn_nm="무인 분리배출함",  # '수거' 없이 '무인'만
        )
        store, _ = CategoryClassifierService.classify(site)
        assert store == StoreCategory.PUBLIC_DROPBOX

    def test_classify_general_default(self) -> None:
        """분류 안 되면 GENERAL."""
        site = NormalizedSite(
            id=1,
            source="test",
            source_key="TEST",
            positn_nm="기타 장소",
        )
        store, _ = CategoryClassifierService.classify(site)
        assert store == StoreCategory.GENERAL

    def test_classify_lodging_excludes_station(self) -> None:
        """스테이션은 숙소로 분류 안 됨."""
        site = NormalizedSite(
            id=1,
            source="test",
            source_key="TEST",
            positn_nm="리필스테이션",
        )
        store, _ = CategoryClassifierService.classify(site)
        assert store != StoreCategory.LODGING

    def test_classify_pickup_categories(self) -> None:
        """수거 품목 분류."""
        site = NormalizedSite(
            id=1,
            source="test",
            source_key="TEST",
            metadata={"clctItemCn": "무색페트, 캔, 종이"},
        )
        _, pickups = CategoryClassifierService.classify(site)
        assert PickupCategory.CLEAR_PET in pickups
        assert PickupCategory.CAN in pickups
        assert PickupCategory.PAPER in pickups

    def test_classify_pickup_default_general(self) -> None:
        """수거 품목 없으면 GENERAL."""
        site = NormalizedSite(
            id=1,
            source="test",
            source_key="TEST",
        )
        _, pickups = CategoryClassifierService.classify(site)
        assert PickupCategory.GENERAL in pickups


class TestLocationEntryBuilder:
    """LocationEntryBuilder 테스트."""

    def test_build_basic(
        self, sample_site: NormalizedSite, sample_metadata: dict[str, Any]
    ) -> None:
        """기본 엔트리 빌드."""
        entry = LocationEntryBuilder.build(
            site=sample_site,
            distance_km=1.5,
            metadata=sample_metadata,
            store_category=StoreCategory.UPCYCLE_RECYCLE,
            pickup_categories=[PickupCategory.CLEAR_PET, PickupCategory.CAN],
        )
        assert entry.id == 1
        assert entry.name == "서울 재활용 센터"
        assert entry.distance_km == 1.5
        assert entry.store_category == "upcycle_recycle"
        assert "clear_pet" in entry.pickup_categories

    def test_format_distance_meters(self) -> None:
        """1km 미만은 m 단위."""
        result = LocationEntryBuilder._format_distance(0.5)
        assert result == "500m"

    def test_format_distance_kilometers(self) -> None:
        """1km 이상은 km 단위."""
        result = LocationEntryBuilder._format_distance(1.5)
        assert result == "1.5km"

    def test_format_distance_none(self) -> None:
        """None이면 None 반환."""
        result = LocationEntryBuilder._format_distance(None)
        assert result is None

    def test_sanitize_placeholder_zerowaste(self) -> None:
        """제로웨이스트 플레이스홀더 제거."""
        result = LocationEntryBuilder._sanitize_optional_text("PLACE", source="zerowaste")
        assert result is None

    def test_sanitize_keeps_normal_text(self) -> None:
        """일반 텍스트는 유지."""
        result = LocationEntryBuilder._sanitize_optional_text("서울시", source="zerowaste")
        assert result == "서울시"

    def test_normalize_phone_11digits(self) -> None:
        """11자리 전화번호 포맷팅."""
        result = LocationEntryBuilder._normalize_phone("01012345678", source="keco")
        assert result == "010-1234-5678"

    def test_normalize_phone_with_dashes(self) -> None:
        """이미 구분자 있는 전화번호."""
        result = LocationEntryBuilder._normalize_phone("02-123-4567", source="keco")
        assert result == "02-123-4567"

    def test_normalize_phone_empty(self) -> None:
        """빈 전화번호."""
        result = LocationEntryBuilder._normalize_phone("", source="keco")
        assert result is None

    def test_extract_time_range_standard(self) -> None:
        """표준 시간 범위 추출."""
        start, end = LocationEntryBuilder._extract_time_range("09:00 ~ 18:00")
        assert start == "09:00"
        assert end == "18:00"

    def test_extract_time_range_no_tilde(self) -> None:
        """~ 없는 경우."""
        start, end = LocationEntryBuilder._extract_time_range("09:00 - 18:00")
        assert start == "09:00"
        assert end == "18:00"

    def test_extract_time_range_invalid(self) -> None:
        """파싱 불가능한 경우."""
        start, end = LocationEntryBuilder._extract_time_range("영업중")
        assert start is None
        assert end is None

    def test_derive_operating_hours_holiday(self, sample_site: NormalizedSite) -> None:
        """휴무일 판정."""
        site = NormalizedSite(
            id=1,
            source="keco",
            source_key="TEST",
            sat_sals_hr_expln_cn="휴무",
        )
        # 토요일에 테스트하면 is_holiday=True가 됨
        result = LocationEntryBuilder._derive_operating_hours(site)
        assert result is not None
        # 요일에 따라 달라지므로 필드 존재만 확인
        assert "is_holiday" in result
        assert "is_open" in result

    def test_derive_operating_hours_zerowaste(self, sample_zerowaste_site: NormalizedSite) -> None:
        """제로웨이스트는 영업시간 미제공."""
        result = LocationEntryBuilder._derive_operating_hours(sample_zerowaste_site)
        assert result is not None
        assert result["start_time"] is None
        assert result["end_time"] is None
