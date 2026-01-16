"""HumanInput Value Objects Unit Tests."""

import pytest

from chat_worker.domain.enums.input_type import InputType
from chat_worker.domain.value_objects.human_input import (
    HumanInputRequest,
    HumanInputResponse,
    LocationData,
)


class TestLocationData:
    """LocationData Value Object 테스트."""

    def test_create(self) -> None:
        """기본 생성."""
        location = LocationData(latitude=37.5665, longitude=126.9780)

        assert location.latitude == 37.5665
        assert location.longitude == 126.9780

    def test_to_dict(self) -> None:
        """딕셔너리 변환."""
        location = LocationData(latitude=37.5665, longitude=126.9780)

        d = location.to_dict()

        assert d["latitude"] == 37.5665
        assert d["longitude"] == 126.9780

    def test_from_dict(self) -> None:
        """딕셔너리에서 생성."""
        data = {"latitude": 37.5665, "longitude": 126.9780}

        location = LocationData.from_dict(data)

        assert location.latitude == 37.5665
        assert location.longitude == 126.9780

    def test_from_dict_string_values(self) -> None:
        """문자열 값에서 생성."""
        data = {"latitude": "37.5665", "longitude": "126.9780"}

        location = LocationData.from_dict(data)

        assert location.latitude == 37.5665
        assert location.longitude == 126.9780

    def test_is_valid_true(self) -> None:
        """유효한 좌표."""
        valid_locations = [
            LocationData(latitude=0, longitude=0),
            LocationData(latitude=90, longitude=180),
            LocationData(latitude=-90, longitude=-180),
            LocationData(latitude=37.5665, longitude=126.9780),
        ]

        for loc in valid_locations:
            assert loc.is_valid() is True

    def test_is_valid_false_latitude(self) -> None:
        """유효하지 않은 위도."""
        invalid = LocationData(latitude=91, longitude=0)
        assert invalid.is_valid() is False

        invalid2 = LocationData(latitude=-91, longitude=0)
        assert invalid2.is_valid() is False

    def test_is_valid_false_longitude(self) -> None:
        """유효하지 않은 경도."""
        invalid = LocationData(latitude=0, longitude=181)
        assert invalid.is_valid() is False

        invalid2 = LocationData(latitude=0, longitude=-181)
        assert invalid2.is_valid() is False

    def test_immutable(self) -> None:
        """불변성 테스트."""
        location = LocationData(latitude=37.5, longitude=127.0)

        with pytest.raises(AttributeError):
            location.latitude = 38.0  # type: ignore


class TestHumanInputRequest:
    """HumanInputRequest Value Object 테스트."""

    def test_create_location_request(self) -> None:
        """위치 요청 생성."""
        request = HumanInputRequest(
            job_id="job-123",
            input_type=InputType.LOCATION,
            message="위치 정보를 제공해주세요",
        )

        assert request.job_id == "job-123"
        assert request.input_type == InputType.LOCATION
        assert request.message == "위치 정보를 제공해주세요"
        assert request.timeout == 60
        assert request.options is None

    def test_create_confirmation_request(self) -> None:
        """확인 요청 생성."""
        request = HumanInputRequest(
            job_id="job-456",
            input_type=InputType.CONFIRMATION,
            message="계속 진행하시겠습니까?",
            timeout=30,
        )

        assert request.input_type == InputType.CONFIRMATION
        assert request.timeout == 30

    def test_create_selection_request(self) -> None:
        """선택 요청 생성."""
        request = HumanInputRequest(
            job_id="job-789",
            input_type=InputType.SELECTION,
            message="재활용 방법을 선택해주세요",
            options=("분리배출", "재활용센터", "대형폐기물"),
        )

        assert request.input_type == InputType.SELECTION
        assert request.options == ("분리배출", "재활용센터", "대형폐기물")

    def test_selection_without_options_raises(self) -> None:
        """SELECTION 타입에 options 없으면 ValueError."""
        with pytest.raises(ValueError, match="SELECTION type requires options"):
            HumanInputRequest(
                job_id="job-123",
                input_type=InputType.SELECTION,
                message="선택해주세요",
            )

    def test_invalid_timeout_raises(self) -> None:
        """timeout <= 0 이면 ValueError."""
        with pytest.raises(ValueError, match="timeout must be positive"):
            HumanInputRequest(
                job_id="job-123",
                input_type=InputType.LOCATION,
                message="위치 요청",
                timeout=0,
            )

        with pytest.raises(ValueError, match="timeout must be positive"):
            HumanInputRequest(
                job_id="job-123",
                input_type=InputType.LOCATION,
                message="위치 요청",
                timeout=-10,
            )

    def test_immutable(self) -> None:
        """불변성 테스트."""
        request = HumanInputRequest(
            job_id="job-123",
            input_type=InputType.LOCATION,
            message="위치 요청",
        )

        with pytest.raises(AttributeError):
            request.job_id = "new-id"  # type: ignore


class TestHumanInputResponse:
    """HumanInputResponse Value Object 테스트."""

    def test_create_basic(self) -> None:
        """기본 생성."""
        response = HumanInputResponse(
            input_type=InputType.LOCATION,
            data={"latitude": 37.5, "longitude": 127.0},
        )

        assert response.input_type == InputType.LOCATION
        assert response.data == {"latitude": 37.5, "longitude": 127.0}
        assert response.cancelled is False
        assert response.timed_out is False

    def test_is_successful_true(self) -> None:
        """성공적인 응답."""
        response = HumanInputResponse(
            input_type=InputType.LOCATION,
            data={"latitude": 37.5, "longitude": 127.0},
        )

        assert response.is_successful is True

    def test_is_successful_false_cancelled(self) -> None:
        """취소된 응답."""
        response = HumanInputResponse(
            input_type=InputType.LOCATION,
            cancelled=True,
        )

        assert response.is_successful is False

    def test_is_successful_false_timed_out(self) -> None:
        """타임아웃 응답."""
        response = HumanInputResponse(
            input_type=InputType.LOCATION,
            timed_out=True,
        )

        assert response.is_successful is False

    def test_is_successful_false_no_data(self) -> None:
        """데이터 없는 응답."""
        response = HumanInputResponse(
            input_type=InputType.LOCATION,
            data=None,
        )

        assert response.is_successful is False

    def test_get_location_success(self) -> None:
        """위치 데이터 추출 성공."""
        response = HumanInputResponse(
            input_type=InputType.LOCATION,
            data={"latitude": 37.5665, "longitude": 126.9780},
        )

        location = response.get_location()

        assert location is not None
        assert location.latitude == 37.5665
        assert location.longitude == 126.9780

    def test_get_location_wrong_type(self) -> None:
        """잘못된 입력 타입."""
        response = HumanInputResponse(
            input_type=InputType.CONFIRMATION,
            data={"confirmed": True},
        )

        assert response.get_location() is None

    def test_get_location_no_data(self) -> None:
        """데이터 없음."""
        response = HumanInputResponse(
            input_type=InputType.LOCATION,
            data=None,
        )

        assert response.get_location() is None

    def test_get_location_invalid_data(self) -> None:
        """잘못된 데이터 형식."""
        response = HumanInputResponse(
            input_type=InputType.LOCATION,
            data={"invalid": "data"},
        )

        assert response.get_location() is None

    def test_cancelled_response_factory(self) -> None:
        """취소 응답 팩토리."""
        response = HumanInputResponse.cancelled_response(InputType.LOCATION)

        assert response.input_type == InputType.LOCATION
        assert response.cancelled is True
        assert response.is_successful is False

    def test_timeout_response_factory(self) -> None:
        """타임아웃 응답 팩토리."""
        response = HumanInputResponse.timeout_response(InputType.CONFIRMATION)

        assert response.input_type == InputType.CONFIRMATION
        assert response.timed_out is True
        assert response.is_successful is False

    def test_success_response_factory(self) -> None:
        """성공 응답 팩토리."""
        response = HumanInputResponse.success_response(
            input_type=InputType.SELECTION,
            data={"selected": "분리배출"},
        )

        assert response.input_type == InputType.SELECTION
        assert response.data == {"selected": "분리배출"}
        assert response.is_successful is True

    def test_immutable(self) -> None:
        """불변성 테스트."""
        response = HumanInputResponse(
            input_type=InputType.LOCATION,
            data={"latitude": 37.5, "longitude": 127.0},
        )

        with pytest.raises(AttributeError):
            response.cancelled = True  # type: ignore
