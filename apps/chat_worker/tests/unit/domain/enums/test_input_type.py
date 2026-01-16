"""InputType Enum Unit Tests."""

import pytest

from chat_worker.domain.enums.input_type import InputType


class TestInputType:
    """InputType Enum 테스트."""

    def test_input_type_values(self) -> None:
        """모든 입력 타입 값 확인."""
        assert InputType.LOCATION.value == "location"
        assert InputType.CONFIRMATION.value == "confirmation"
        assert InputType.SELECTION.value == "selection"
        assert InputType.CANCEL.value == "cancel"

    def test_from_string_valid(self) -> None:
        """유효한 문자열에서 생성."""
        assert InputType.from_string("location") == InputType.LOCATION
        assert InputType.from_string("confirmation") == InputType.CONFIRMATION
        assert InputType.from_string("selection") == InputType.SELECTION
        assert InputType.from_string("cancel") == InputType.CANCEL

    def test_from_string_case_insensitive(self) -> None:
        """대소문자 구분 없이 변환."""
        assert InputType.from_string("LOCATION") == InputType.LOCATION
        assert InputType.from_string("Location") == InputType.LOCATION
        assert InputType.from_string("  location  ") == InputType.LOCATION

    def test_from_string_invalid_raises(self) -> None:
        """유효하지 않은 문자열은 ValueError."""
        with pytest.raises(ValueError, match="Invalid input type"):
            InputType.from_string("invalid")

        with pytest.raises(ValueError, match="Invalid input type"):
            InputType.from_string("")

    def test_requires_data_location(self) -> None:
        """LOCATION은 데이터 필요."""
        assert InputType.LOCATION.requires_data() is True

    def test_requires_data_selection(self) -> None:
        """SELECTION은 데이터 필요."""
        assert InputType.SELECTION.requires_data() is True

    def test_requires_data_confirmation(self) -> None:
        """CONFIRMATION은 데이터 불필요."""
        assert InputType.CONFIRMATION.requires_data() is False

    def test_requires_data_cancel(self) -> None:
        """CANCEL은 데이터 불필요."""
        assert InputType.CANCEL.requires_data() is False

    def test_input_type_is_string_enum(self) -> None:
        """InputType는 str 기반 Enum."""
        assert isinstance(InputType.LOCATION.value, str)
        assert InputType.LOCATION.value == "location"

    def test_input_type_count(self) -> None:
        """총 입력 타입 수 확인."""
        all_types = list(InputType)
        assert len(all_types) == 4

    def test_input_type_comparison(self) -> None:
        """입력 타입 비교."""
        assert InputType.LOCATION == InputType.LOCATION
        assert InputType.LOCATION != InputType.CANCEL
        assert InputType.LOCATION == "location"
