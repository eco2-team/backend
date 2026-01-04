"""Domain Layer 단위 테스트."""

from __future__ import annotations

import pytest

from apps.location.domain.entities import NormalizedSite
from apps.location.domain.enums import PickupCategory, StoreCategory
from apps.location.domain.value_objects import Coordinates


class TestCoordinates:
    """Coordinates Value Object 테스트."""

    def test_valid_coordinates(self) -> None:
        """유효한 좌표 생성."""
        coords = Coordinates(latitude=37.5665, longitude=126.978)
        assert coords.latitude == 37.5665
        assert coords.longitude == 126.978

    def test_invalid_latitude_too_low(self) -> None:
        """위도가 -90 미만이면 에러."""
        with pytest.raises(ValueError, match="Invalid latitude"):
            Coordinates(latitude=-91, longitude=0)

    def test_invalid_latitude_too_high(self) -> None:
        """위도가 90 초과이면 에러."""
        with pytest.raises(ValueError, match="Invalid latitude"):
            Coordinates(latitude=91, longitude=0)

    def test_invalid_longitude_too_low(self) -> None:
        """경도가 -180 미만이면 에러."""
        with pytest.raises(ValueError, match="Invalid longitude"):
            Coordinates(latitude=0, longitude=-181)

    def test_invalid_longitude_too_high(self) -> None:
        """경도가 180 초과이면 에러."""
        with pytest.raises(ValueError, match="Invalid longitude"):
            Coordinates(latitude=0, longitude=181)

    def test_boundary_values(self) -> None:
        """경계값 테스트."""
        coords = Coordinates(latitude=90, longitude=180)
        assert coords.latitude == 90
        assert coords.longitude == 180

        coords = Coordinates(latitude=-90, longitude=-180)
        assert coords.latitude == -90
        assert coords.longitude == -180


class TestNormalizedSite:
    """NormalizedSite Entity 테스트."""

    def test_coordinates_returns_value_object(self, sample_site: NormalizedSite) -> None:
        """좌표가 있으면 Coordinates 반환."""
        coords = sample_site.coordinates()
        assert coords is not None
        assert coords.latitude == 37.5665
        assert coords.longitude == 126.978

    def test_coordinates_returns_none_when_missing(self) -> None:
        """좌표가 없으면 None 반환."""
        site = NormalizedSite(id=1, source="test", source_key="TEST-001")
        assert site.coordinates() is None

    def test_coordinates_returns_none_when_partial(self) -> None:
        """위도/경도 중 하나만 있으면 None 반환."""
        site = NormalizedSite(
            id=1,
            source="test",
            source_key="TEST-001",
            positn_pstn_lat=37.5665,
        )
        assert site.coordinates() is None


class TestEnums:
    """Enum 테스트."""

    def test_store_category_values(self) -> None:
        """StoreCategory 값 확인."""
        assert StoreCategory.REFILL_ZERO.value == "refill_zero"
        assert StoreCategory.CAFE_BAKERY.value == "cafe_bakery"
        assert StoreCategory.GENERAL.value == "general"

    def test_pickup_category_values(self) -> None:
        """PickupCategory 값 확인."""
        assert PickupCategory.CLEAR_PET.value == "clear_pet"
        assert PickupCategory.CAN.value == "can"
        assert PickupCategory.GENERAL.value == "general"

    def test_enum_from_string(self) -> None:
        """문자열에서 Enum 생성."""
        assert StoreCategory("refill_zero") == StoreCategory.REFILL_ZERO
        assert PickupCategory("clear_pet") == PickupCategory.CLEAR_PET

    def test_invalid_enum_raises_error(self) -> None:
        """잘못된 문자열이면 에러."""
        with pytest.raises(ValueError):
            StoreCategory("invalid")
        with pytest.raises(ValueError):
            PickupCategory("invalid")
