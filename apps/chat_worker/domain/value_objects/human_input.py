"""HumanInput Value Objects - Human-in-the-Loop 도메인 객체.

사용자 입력 요청과 응답을 표현하는 불변 객체입니다.

비즈니스 규칙:
- HumanInputRequest: 사용자에게 요청할 입력 정보
- HumanInputResponse: 사용자로부터 받은 응답
- LocationData: 위치 정보 (Geolocation API 형식)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from chat_worker.domain.enums.input_type import InputType


@dataclass(frozen=True)
class LocationData:
    """위치 정보 (Geolocation API 형식).

    Attributes:
        latitude: 위도
        longitude: 경도
    """

    latitude: float
    longitude: float

    def to_dict(self) -> dict[str, float]:
        """딕셔너리로 변환."""
        return {"latitude": self.latitude, "longitude": self.longitude}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LocationData":
        """딕셔너리에서 생성."""
        return cls(
            latitude=float(data["latitude"]),
            longitude=float(data["longitude"]),
        )

    def is_valid(self) -> bool:
        """유효한 좌표인지 검증."""
        return -90 <= self.latitude <= 90 and -180 <= self.longitude <= 180


@dataclass(frozen=True)
class HumanInputRequest:
    """사용자 입력 요청.

    Worker가 사용자에게 추가 입력을 요청할 때 사용.

    Attributes:
        job_id: 작업 ID
        input_type: 요청하는 입력 타입
        message: 사용자에게 표시할 메시지
        timeout: 응답 대기 시간 (초)
        options: 선택지 (SELECTION 타입일 때)
    """

    job_id: str
    input_type: InputType
    message: str
    timeout: int = 60
    options: tuple[str, ...] | None = None

    def __post_init__(self):
        """유효성 검증."""
        if self.input_type == InputType.SELECTION and not self.options:
            raise ValueError("SELECTION type requires options")
        if self.timeout <= 0:
            raise ValueError("timeout must be positive")


@dataclass(frozen=True)
class HumanInputResponse:
    """사용자 입력 응답.

    Attributes:
        input_type: 응답 타입
        data: 응답 데이터 (타입에 따라 다름)
        cancelled: 사용자가 취소했는지
        timed_out: 타임아웃 여부
    """

    input_type: InputType
    data: dict[str, Any] | None = None
    cancelled: bool = False
    timed_out: bool = False

    @property
    def is_successful(self) -> bool:
        """성공적인 응답인지."""
        return not self.cancelled and not self.timed_out and self.data is not None

    def get_location(self) -> LocationData | None:
        """위치 데이터 추출.

        Returns:
            LocationData 또는 None
        """
        if self.input_type != InputType.LOCATION or not self.data:
            return None
        try:
            return LocationData.from_dict(self.data)
        except (KeyError, ValueError):
            return None

    @classmethod
    def cancelled_response(cls, input_type: InputType) -> "HumanInputResponse":
        """취소 응답 생성."""
        return cls(input_type=input_type, cancelled=True)

    @classmethod
    def timeout_response(cls, input_type: InputType) -> "HumanInputResponse":
        """타임아웃 응답 생성."""
        return cls(input_type=input_type, timed_out=True)

    @classmethod
    def success_response(
        cls,
        input_type: InputType,
        data: dict[str, Any],
    ) -> "HumanInputResponse":
        """성공 응답 생성."""
        return cls(input_type=input_type, data=data)
