"""Weather Client Port - 기상청 API 추상화.

Clean Architecture:
- Port: 이 파일 (추상 인터페이스 + DTO)
- Adapter: infrastructure/integrations/kma/kma_weather_http_client.py

기상청 단기예보 API (공공데이터포털):
- 초단기실황: 현재 기온, 강수량
- 단기예보: 오늘/내일 강수확률, 기온

참고:
- https://www.data.go.kr/data/15084084/openapi.do
- https://apihub.kma.go.kr/
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import IntEnum


class PrecipitationType(IntEnum):
    """강수 형태.

    기상청 PTY 코드:
    - 0: 없음
    - 1: 비
    - 2: 비/눈
    - 3: 눈
    - 4: 소나기
    """

    NONE = 0
    RAIN = 1
    RAIN_SNOW = 2
    SNOW = 3
    SHOWER = 4


class SkyStatus(IntEnum):
    """하늘 상태.

    기상청 SKY 코드:
    - 1: 맑음
    - 3: 구름많음
    - 4: 흐림
    """

    CLEAR = 1
    PARTLY_CLOUDY = 3
    CLOUDY = 4


@dataclass(frozen=True)
class CurrentWeatherDTO:
    """현재 날씨 정보 (초단기실황)."""

    temperature: float  # 기온 (°C), T1H
    precipitation: float  # 1시간 강수량 (mm), RN1
    precipitation_type: PrecipitationType  # 강수형태, PTY
    humidity: int  # 습도 (%), REH
    sky_status: SkyStatus  # 하늘상태, SKY
    wind_speed: float = 0.0  # 풍속 (m/s), WSD


@dataclass(frozen=True)
class WeatherForecastDTO:
    """예보 정보 (단기예보)."""

    date: str  # YYYYMMDD
    time: str  # HHMM
    temperature: float | None  # 기온 (°C), TMP
    precipitation_prob: int  # 강수확률 (%), POP
    precipitation_type: PrecipitationType  # 강수형태, PTY
    sky_status: SkyStatus  # 하늘상태, SKY


@dataclass(frozen=True)
class WeatherResponse:
    """날씨 API 응답."""

    success: bool
    current: CurrentWeatherDTO | None = None
    forecasts: list[WeatherForecastDTO] = field(default_factory=list)
    error_message: str | None = None
    nx: int | None = None  # 조회된 격자 X 좌표
    ny: int | None = None  # 조회된 격자 Y 좌표


class WeatherClientPort(ABC):
    """기상청 날씨 클라이언트 Port.

    추상 인터페이스 - Application Layer에서 사용.
    실제 구현은 Infrastructure Layer의 Adapter에서.
    """

    @abstractmethod
    async def get_current_weather(self, nx: int, ny: int) -> WeatherResponse:
        """현재 날씨 조회 (초단기실황).

        Args:
            nx: 기상청 격자 X 좌표
            ny: 기상청 격자 Y 좌표

        Returns:
            WeatherResponse (current 필드에 현재 날씨)
        """
        pass

    @abstractmethod
    async def get_forecast(
        self, nx: int, ny: int, hours: int = 24
    ) -> WeatherResponse:
        """단기예보 조회.

        Args:
            nx: 기상청 격자 X 좌표
            ny: 기상청 격자 Y 좌표
            hours: 조회할 시간 범위 (기본 24시간)

        Returns:
            WeatherResponse (forecasts 필드에 예보 목록)
        """
        pass

    @abstractmethod
    async def close(self) -> None:
        """리소스 정리."""
        pass


__all__ = [
    "WeatherClientPort",
    "WeatherResponse",
    "CurrentWeatherDTO",
    "WeatherForecastDTO",
    "PrecipitationType",
    "SkyStatus",
]
