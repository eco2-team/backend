"""Unit tests for LocationService."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from domains.location.services.location import LocationService


class TestLocationServiceHelpers:
    """Tests for LocationService helper methods."""

    def test_format_distance_meters(self):
        """Distance under 1km should display in meters."""
        result = LocationService._format_distance(0.5)
        assert result == "500m"

    def test_format_distance_kilometers(self):
        """Distance 1km or more should display in km."""
        result = LocationService._format_distance(2.5)
        assert result == "2.5km"

    def test_format_distance_none(self):
        """None distance should return None."""
        result = LocationService._format_distance(None)
        assert result is None

    def test_first_non_empty_returns_first_valid(self):
        """Should return first non-empty string value."""
        result = LocationService._first_non_empty(
            None, "", "valid", "also valid", fallback="fallback"
        )
        assert result == "valid"

    def test_first_non_empty_returns_fallback(self):
        """Should return fallback when all values are empty."""
        result = LocationService._first_non_empty(None, "", None, fallback="fallback")
        assert result == "fallback"

    def test_normalize_phone_11_digits(self):
        """11-digit phone should be formatted correctly."""
        result = LocationService._normalize_phone("01012345678", source="keco")
        assert result == "010-1234-5678"

    def test_normalize_phone_with_dashes(self):
        """Phone with dashes should be normalized."""
        result = LocationService._normalize_phone("010-1234-5678", source="keco")
        assert result == "010-1234-5678"

    def test_normalize_phone_empty(self):
        """Empty phone should return None."""
        result = LocationService._normalize_phone("", source="keco")
        assert result is None

    def test_sanitize_optional_text_placeholder(self):
        """Placeholder markers should be sanitized for zerowaste source."""
        result = LocationService._sanitize_optional_text("PHONE", source="zerowaste")
        assert result is None

    def test_sanitize_optional_text_valid(self):
        """Valid text should pass through."""
        result = LocationService._sanitize_optional_text("서울시 강남구", source="keco")
        assert result == "서울시 강남구"

    def test_extract_time_range_standard(self):
        """Standard time range should be extracted."""
        start, end = LocationService._extract_time_range("09:00 ~ 18:00")
        assert start == "09:00"
        assert end == "18:00"

    def test_extract_time_range_no_match(self):
        """No time range should return None, None."""
        start, end = LocationService._extract_time_range("휴무")
        assert start is None
        assert end is None

    def test_extract_time_range_with_tilde_only(self):
        """Time range with tilde but no times."""
        start, end = LocationService._extract_time_range("오전 ~ 오후")
        assert start == "오전"
        assert end == "오후"

    def test_extract_time_range_multiple_times(self):
        """Multiple times in string."""
        start, end = LocationService._extract_time_range("점심 12:00 저녁 18:00 마감")
        assert start == "12:00"
        assert end == "18:00"

    def test_sanitize_optional_text_none(self):
        """None should return None."""
        result = LocationService._sanitize_optional_text(None, source="keco")
        assert result is None

    def test_sanitize_optional_text_empty(self):
        """Empty string should return None."""
        result = LocationService._sanitize_optional_text("   ", source="keco")
        assert result is None

    def test_normalize_phone_three_groups(self):
        """Phone with 3 groups should be joined."""
        result = LocationService._normalize_phone("02-1234-5678", source="keco")
        assert result == "02-1234-5678"

    def test_normalize_phone_no_digits(self):
        """No digits should return None."""
        result = LocationService._normalize_phone("전화없음", source="keco")
        assert result is None


class TestNearbyCenters:
    """Tests for nearby_centers method."""

    @pytest.fixture
    def mock_service(self):
        """Create LocationService with mocked dependencies."""
        service = LocationService.__new__(LocationService)
        service.repo = MagicMock()
        service.settings = MagicMock()
        service.settings.metrics_cache_ttl_seconds = 60
        return service

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_results(self, mock_service):
        """결과가 없으면 빈 리스트를 반환합니다."""
        mock_service.repo.find_within_radius = AsyncMock(return_value=[])

        result = await mock_service.nearby_centers(
            lat=37.5665,
            lon=126.9780,
            radius=1000,
            zoom=None,
            store_filter=None,
            pickup_filter=None,
        )

        assert result == []

    @pytest.mark.asyncio
    async def test_filters_by_store_category(self, mock_service):
        """store_filter로 필터링합니다."""
        from domains.location.domain.value_objects import StoreCategory

        mock_site = MagicMock()
        mock_site.id = 1
        mock_site.source = "keco"
        mock_site.positn_nm = "테스트 센터"
        mock_site.positn_rdnm_addr = "서울시 강남구"
        mock_site.positn_lotno_addr = None
        mock_site.positn_intdc_cn = None
        mock_site.positn_pstn_add_expln = None
        mock_site.metadata = {"recycle_items": ["general"]}
        mock_site.coordinates = MagicMock(return_value=MagicMock(latitude=37.5, longitude=127.0))
        mock_site.mon_sals_hr_expln_cn = None

        mock_service.repo.find_within_radius = AsyncMock(return_value=[(mock_site, 0.5)])

        # 다른 카테고리로 필터링하면 빈 결과
        result = await mock_service.nearby_centers(
            lat=37.5665,
            lon=126.9780,
            radius=1000,
            zoom=None,
            store_filter={StoreCategory.REFILL_ZERO},
            pickup_filter=None,
        )

        assert len(result) == 0


class TestMetrics:
    """Tests for metrics method."""

    @pytest.fixture
    def mock_service(self):
        """Create LocationService with mocked dependencies."""
        service = LocationService.__new__(LocationService)
        service.repo = MagicMock()
        service.settings = MagicMock()
        service.settings.metrics_cache_ttl_seconds = 60
        return service

    @pytest.mark.asyncio
    async def test_returns_cached_metrics(self, mock_service):
        """캐시된 메트릭스를 반환합니다."""
        from unittest.mock import patch

        with patch("domains.location.services.location.RedisCache") as mock_cache:
            mock_cache.get = AsyncMock(return_value="100")

            result = await mock_service.metrics()

            assert result["indexed_sites"] == 100

    @pytest.mark.asyncio
    async def test_fetches_and_caches_metrics(self, mock_service):
        """캐시 미스 시 DB에서 조회하고 캐시합니다."""
        from unittest.mock import patch

        with patch("domains.location.services.location.RedisCache") as mock_cache:
            mock_cache.get = AsyncMock(return_value=None)
            mock_cache.set = AsyncMock()
            mock_service.repo.count_sites = AsyncMock(return_value=500)

            result = await mock_service.metrics()

            assert result["indexed_sites"] == 500
            mock_cache.set.assert_called_once()


class TestDeriveOperatingHours:
    """Tests for _derive_operating_hours method."""

    def test_zerowaste_returns_empty_payload(self):
        """zerowaste 소스는 빈 payload를 반환합니다."""
        mock_site = MagicMock()
        mock_site.source = "zerowaste"

        result = LocationService._derive_operating_hours(mock_site)

        assert result["is_holiday"] is None
        assert result["is_open"] is False

    def test_holiday_detected(self):
        """휴무일을 감지합니다."""
        mock_site = MagicMock()
        mock_site.source = "keco"
        # 현재 요일에 해당하는 속성 설정
        from datetime import datetime
        from zoneinfo import ZoneInfo

        today = datetime.now(ZoneInfo("Asia/Seoul"))
        attr_name = LocationService.WEEKDAY_LABELS[today.weekday()][0]
        setattr(mock_site, attr_name, "휴무")

        result = LocationService._derive_operating_hours(mock_site)

        assert result["is_holiday"] is True


class TestDerivePhone:
    """Tests for _derive_phone method."""

    def test_returns_first_valid_phone(self):
        """첫 번째 유효한 전화번호를 반환합니다."""
        mock_site = MagicMock()
        mock_site.source = "keco"

        result = LocationService._derive_phone(
            mock_site,
            {"bscTelnoCn": "02-1234-5678"},
        )

        assert result == "02-1234-5678"

    def test_returns_none_when_no_phone(self):
        """전화번호가 없으면 None을 반환합니다."""
        mock_site = MagicMock()
        mock_site.source = "keco"

        result = LocationService._derive_phone(mock_site, {})

        assert result is None


class TestToTodayDatetime:
    """Tests for _to_today_datetime method."""

    def test_valid_time_string(self):
        """유효한 시간 문자열을 파싱합니다."""
        result = LocationService._to_today_datetime("09:00")

        assert result is not None
        assert result.hour == 9
        assert result.minute == 0

    def test_invalid_time_string(self):
        """유효하지 않은 시간 문자열은 None을 반환합니다."""
        result = LocationService._to_today_datetime("invalid")

        assert result is None


class TestDeriveRoadAddress:
    """Tests for _derive_road_address method."""

    def test_returns_road_address_first(self):
        """도로명 주소를 우선 반환합니다."""
        mock_site = MagicMock()
        mock_site.positn_rdnm_addr = "서울시 강남구 테헤란로"
        mock_site.positn_lotno_addr = "강남구 123-45"
        mock_site.positn_pstn_add_expln = None

        result = LocationService._derive_road_address(mock_site, {})

        assert result == "서울시 강남구 테헤란로"


class TestZoomPolicy:
    """Tests for zoom_policy module."""

    def test_radius_from_zoom_none(self):
        """zoom이 None이면 기본값을 반환합니다."""
        from domains.location.services.zoom_policy import radius_from_zoom, DEFAULT_RADIUS_METERS

        assert radius_from_zoom(None) == DEFAULT_RADIUS_METERS

    def test_radius_from_zoom_with_value(self):
        """zoom 값에 따른 반경을 반환합니다."""
        from domains.location.services.zoom_policy import radius_from_zoom

        # Kakao zoom 1 (거리) → 내부 높은 레벨 → 작은 반경
        result = radius_from_zoom(1)
        assert result > 0

    def test_limit_from_zoom_none(self):
        """zoom이 None이면 기본값을 반환합니다."""
        from domains.location.services.zoom_policy import limit_from_zoom

        assert limit_from_zoom(None) == 200

    def test_limit_from_zoom_with_value(self):
        """zoom 값에 따른 limit을 반환합니다."""
        from domains.location.services.zoom_policy import limit_from_zoom

        result = limit_from_zoom(1)
        assert result > 0
