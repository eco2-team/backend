"""HTTP Controllers 단위 테스트."""

from __future__ import annotations


import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from apps.location.domain.enums import PickupCategory, StoreCategory
from apps.location.main import app
from apps.location.presentation.http.controllers.location import (
    _parse_pickup_category_param,
    _parse_store_category_param,
)


@pytest.fixture
def client() -> TestClient:
    """TestClient 인스턴스."""
    return TestClient(app)


class TestParseStoreCategoryParam:
    """_parse_store_category_param 테스트."""

    def test_all_returns_none(self) -> None:
        """'all'이면 None 반환."""
        assert _parse_store_category_param("all") is None
        assert _parse_store_category_param("ALL") is None
        assert _parse_store_category_param("") is None

    def test_single_value(self) -> None:
        """단일 값 파싱."""
        result = _parse_store_category_param("refill_zero")
        assert result == {StoreCategory.REFILL_ZERO}

    def test_multiple_values(self) -> None:
        """쉼표로 구분된 값 파싱."""
        result = _parse_store_category_param("refill_zero,cafe_bakery")
        assert result == {StoreCategory.REFILL_ZERO, StoreCategory.CAFE_BAKERY}

    def test_invalid_value_raises_error(self) -> None:
        """잘못된 값이면 HTTPException."""
        with pytest.raises(HTTPException) as exc_info:
            _parse_store_category_param("invalid_category")
        assert exc_info.value.status_code == 400
        assert "Invalid store_category" in exc_info.value.detail

    def test_whitespace_handling(self) -> None:
        """공백 처리."""
        result = _parse_store_category_param("  refill_zero  ,  cafe_bakery  ")
        assert result == {StoreCategory.REFILL_ZERO, StoreCategory.CAFE_BAKERY}


class TestParsePickupCategoryParam:
    """_parse_pickup_category_param 테스트."""

    def test_all_returns_none(self) -> None:
        """'all'이면 None 반환."""
        assert _parse_pickup_category_param("all") is None
        assert _parse_pickup_category_param("ALL") is None
        assert _parse_pickup_category_param("") is None

    def test_single_value(self) -> None:
        """단일 값 파싱."""
        result = _parse_pickup_category_param("clear_pet")
        assert result == {PickupCategory.CLEAR_PET}

    def test_multiple_values(self) -> None:
        """쉼표로 구분된 값 파싱."""
        result = _parse_pickup_category_param("clear_pet,can,paper")
        assert result == {PickupCategory.CLEAR_PET, PickupCategory.CAN, PickupCategory.PAPER}

    def test_invalid_value_raises_error(self) -> None:
        """잘못된 값이면 HTTPException."""
        with pytest.raises(HTTPException) as exc_info:
            _parse_pickup_category_param("invalid_pickup")
        assert exc_info.value.status_code == 400
        assert "Invalid pickup_category" in exc_info.value.detail


class TestHealthController:
    """Health Controller 테스트."""

    def test_health_check(self, client: TestClient) -> None:
        """헬스체크 엔드포인트."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "location-api"

    def test_ping(self, client: TestClient) -> None:
        """Ping 엔드포인트."""
        response = client.get("/ping")
        assert response.status_code == 200
        assert response.json()["pong"] is True


class TestLocationController:
    """Location Controller 테스트."""

    def test_centers_missing_lat(self, client: TestClient) -> None:
        """위도 누락 시 에러."""
        response = client.get("/api/v1/locations/centers?lon=126.978")
        assert response.status_code == 422

    def test_centers_missing_lon(self, client: TestClient) -> None:
        """경도 누락 시 에러."""
        response = client.get("/api/v1/locations/centers?lat=37.5665")
        assert response.status_code == 422

    def test_centers_invalid_lat(self, client: TestClient) -> None:
        """잘못된 위도 범위."""
        response = client.get("/api/v1/locations/centers?lat=100&lon=126.978")
        assert response.status_code == 422

    def test_centers_invalid_lon(self, client: TestClient) -> None:
        """잘못된 경도 범위."""
        response = client.get("/api/v1/locations/centers?lat=37.5665&lon=200")
        assert response.status_code == 422

    def test_centers_invalid_store_category(self, client: TestClient) -> None:
        """잘못된 store_category."""
        response = client.get(
            "/api/v1/locations/centers?lat=37.5665&lon=126.978&store_category=invalid"
        )
        assert response.status_code == 400

    def test_centers_invalid_pickup_category(self, client: TestClient) -> None:
        """잘못된 pickup_category."""
        response = client.get(
            "/api/v1/locations/centers?lat=37.5665&lon=126.978&pickup_category=invalid"
        )
        assert response.status_code == 400
