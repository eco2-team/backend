"""LocationService 단위 테스트.

LocationService는 순수 로직만 담당 (Port 의존 없음):
- to_answer_context: 컨텍스트 변환
- validate_location: 위치 검증
- build_no_location_context: 위치 정보 없음 컨텍스트
- build_not_found_context: 결과 없음 컨텍스트
"""

from __future__ import annotations

import pytest

from chat_worker.application.ports.location_client import LocationDTO
from chat_worker.application.services.location_service import LocationService
from chat_worker.domain import LocationData


def create_location_dto(
    id: int = 1,
    name: str = "테스트 센터",
    road_address: str = "서울시 강남구 테스트로 123",
    distance_km: float = 1.5,
    distance_text: str = "1.5km",
    is_open: bool = True,
    phone: str | None = "02-1234-5678",
    pickup_categories: list[str] | None = None,
) -> LocationDTO:
    """LocationDTO 팩토리."""
    return LocationDTO(
        id=id,
        name=name,
        road_address=road_address,
        latitude=37.5665,
        longitude=126.9780,
        distance_km=distance_km,
        distance_text=distance_text,
        store_category="재활용센터",
        pickup_categories=pickup_categories or ["플라스틱", "종이"],
        is_open=is_open,
        phone=phone,
    )


class TestLocationService:
    """LocationService 테스트 스위트 (순수 로직)."""

    @pytest.fixture
    def sample_centers(self) -> list[LocationDTO]:
        """샘플 센터 목록."""
        return [
            create_location_dto(id=1, name="센터A", distance_km=0.5),
            create_location_dto(id=2, name="센터B", distance_km=1.2),
            create_location_dto(id=3, name="센터C", distance_km=2.0),
        ]

    @pytest.fixture
    def user_location(self) -> LocationData:
        """사용자 위치."""
        return LocationData(latitude=37.5665, longitude=126.9780)

    # ==========================================================
    # to_answer_context Tests
    # ==========================================================

    def test_to_answer_context_with_centers(
        self,
        sample_centers: list[LocationDTO],
        user_location: LocationData,
    ):
        """센터 있는 경우 컨텍스트."""
        context = LocationService.to_answer_context(
            locations=sample_centers,
            user_location=user_location,
        )

        assert context["found"] is True
        assert context["count"] == 3
        assert "centers" in context
        assert len(context["centers"]) == 3
        assert context["centers"][0]["name"] == "센터A"

    def test_to_answer_context_empty(self):
        """빈 결과 컨텍스트."""
        context = LocationService.to_answer_context(locations=[])

        assert context["found"] is False
        assert context["count"] == 0
        assert "message" in context
        assert "찾지 못했어요" in context["message"]

    def test_to_answer_context_without_user_location(
        self,
        sample_centers: list[LocationDTO],
    ):
        """사용자 위치 없이."""
        context = LocationService.to_answer_context(locations=sample_centers)

        assert "user_location" not in context
        assert context["found"] is True

    def test_to_answer_context_with_user_location(
        self,
        sample_centers: list[LocationDTO],
        user_location: LocationData,
    ):
        """사용자 위치 포함."""
        context = LocationService.to_answer_context(
            locations=sample_centers,
            user_location=user_location,
        )

        assert "user_location" in context
        assert context["user_location"]["latitude"] == user_location.latitude

    def test_to_answer_context_center_structure(self):
        """센터 구조 확인."""
        center = create_location_dto(
            name="테스트센터",
            road_address="테스트주소",
            distance_text="500m",
            is_open=True,
            phone="010-1234-5678",
            pickup_categories=["플라스틱"],
        )

        context = LocationService.to_answer_context([center])

        center_ctx = context["centers"][0]
        assert center_ctx["name"] == "테스트센터"
        assert center_ctx["address"] == "테스트주소"
        assert center_ctx["distance"] == "500m"
        assert center_ctx["is_open"] is True
        assert center_ctx["phone"] == "010-1234-5678"
        assert center_ctx["categories"] == ["플라스틱"]

    # ==========================================================
    # validate_location Tests
    # ==========================================================

    def test_validate_location_valid(self, user_location: LocationData):
        """유효한 위치 검증."""
        assert LocationService.validate_location(user_location) is True

    def test_validate_location_none(self):
        """None 위치 검증."""
        assert LocationService.validate_location(None) is False

    def test_validate_location_zero_coordinates(self):
        """좌표가 0인 경우."""
        location = LocationData(latitude=0.0, longitude=0.0)
        assert LocationService.validate_location(location) is False

    def test_validate_location_zero_latitude_only(self):
        """위도만 0인 경우."""
        location = LocationData(latitude=0.0, longitude=126.9780)
        assert LocationService.validate_location(location) is False

    # ==========================================================
    # build_no_location_context Tests
    # ==========================================================

    def test_build_no_location_context(self):
        """위치 정보 없음 컨텍스트."""
        context = LocationService.build_no_location_context()

        assert context["found"] is False
        assert context["count"] == 0
        assert context["error"] == "location_not_provided"
        assert "위치 정보가 필요해요" in context["message"]

    # ==========================================================
    # build_not_found_context Tests
    # ==========================================================

    def test_build_not_found_context(self, user_location: LocationData):
        """결과 없음 컨텍스트."""
        context = LocationService.build_not_found_context(user_location)

        assert context["found"] is False
        assert context["count"] == 0
        assert "user_location" in context
        assert "찾지 못했어요" in context["message"]
