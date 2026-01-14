"""InputType Enum - Human-in-the-Loop 입력 타입.

사용자에게 요청할 수 있는 추가 입력 종류를 정의합니다.

비즈니스 규칙:
- LOCATION: 위치 정보 (Geolocation API)
- CONFIRMATION: 확인/취소 (Yes/No)
- SELECTION: 선택지 중 하나 (Multiple Choice)
- CANCEL: 사용자가 요청을 취소함
"""

from __future__ import annotations

from enum import Enum


class InputType(str, Enum):
    """Human-in-the-Loop 입력 타입."""

    # 위치 정보 요청 (Geolocation API)
    LOCATION = "location"

    # 확인 요청 (Yes/No)
    CONFIRMATION = "confirmation"

    # 선택 요청 (Multiple Choice)
    SELECTION = "selection"

    # 사용자 취소
    CANCEL = "cancel"

    @classmethod
    def from_string(cls, value: str) -> "InputType":
        """문자열에서 InputType으로 변환.

        Args:
            value: 입력 타입 문자열

        Returns:
            InputType Enum

        Raises:
            ValueError: 유효하지 않은 입력 타입
        """
        value_lower = value.lower().strip()
        for input_type in cls:
            if input_type.value == value_lower:
                return input_type
        raise ValueError(f"Invalid input type: {value}")

    def requires_data(self) -> bool:
        """이 입력 타입이 추가 데이터를 필요로 하는지.

        Returns:
            True if data is required (e.g., LOCATION needs coordinates)
        """
        return self in {InputType.LOCATION, InputType.SELECTION}
