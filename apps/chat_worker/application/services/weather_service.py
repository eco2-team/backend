"""Weather Service - 순수 비즈니스 로직.

Port 의존 없이 순수 로직만 담당:
- 위경도 → 격자좌표 변환 (LCC 투영)
- 날씨 기반 분리배출 팁 생성

Clean Architecture:
- Service: 이 파일 (순수 로직, Port 의존 없음)
- Port: application/ports/weather_client.py (인터페이스)
- Adapter: infrastructure/integrations/kma/ (HTTP 구현)

좌표 변환 참고:
- 기상청 격자 좌표 변환 공식 (Lambert Conformal Conic)
- https://www.kma.go.kr/weather/forecast/timeseries.jsp
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from chat_worker.application.ports.weather_client import (
    CurrentWeatherDTO,
    PrecipitationType,
)


# ===== 기상청 격자 변환 상수 =====
# LCC (Lambert Conformal Conic) 투영 파라미터
# 기상청 제공 표준 값

@dataclass(frozen=True)
class LccParameters:
    """LCC 투영 파라미터."""

    re: float = 6371.00877  # 지구 반경 (km)
    grid: float = 5.0  # 격자 간격 (km)
    slat1: float = 30.0  # 표준 위도 1 (degree)
    slat2: float = 60.0  # 표준 위도 2 (degree)
    olon: float = 126.0  # 기준점 경도 (degree)
    olat: float = 38.0  # 기준점 위도 (degree)
    xo: int = 43  # 기준점 X 좌표 (격자)
    yo: int = 136  # 기준점 Y 좌표 (격자)


LCC = LccParameters()


class WeatherService:
    """날씨 서비스 (순수 로직).

    Port 의존 없이:
    - 위경도 → 격자좌표 변환
    - 날씨 기반 분리배출 팁 생성
    """

    @staticmethod
    def convert_to_grid(lat: float, lon: float) -> tuple[int, int]:
        """위경도 → 기상청 격자좌표 변환.

        Lambert Conformal Conic (LCC) 투영 변환.
        기상청 공식 변환 알고리즘 적용.

        Args:
            lat: 위도 (degree)
            lon: 경도 (degree)

        Returns:
            (nx, ny) 기상청 격자 좌표

        Example:
            >>> nx, ny = WeatherService.convert_to_grid(37.5665, 126.9780)
            >>> print(f"서울 시청: ({nx}, {ny})")  # (60, 127)
        """
        degrad = math.pi / 180.0

        re = LCC.re / LCC.grid
        slat1 = LCC.slat1 * degrad
        slat2 = LCC.slat2 * degrad
        olon = LCC.olon * degrad
        olat = LCC.olat * degrad

        # LCC 투영 계산
        sn = math.tan(math.pi * 0.25 + slat2 * 0.5) / math.tan(
            math.pi * 0.25 + slat1 * 0.5
        )
        sn = math.log(math.cos(slat1) / math.cos(slat2)) / math.log(sn)

        sf = math.tan(math.pi * 0.25 + slat1 * 0.5)
        sf = math.pow(sf, sn) * math.cos(slat1) / sn

        ro = math.tan(math.pi * 0.25 + olat * 0.5)
        ro = re * sf / math.pow(ro, sn)

        ra = math.tan(math.pi * 0.25 + lat * degrad * 0.5)
        ra = re * sf / math.pow(ra, sn)

        theta = lon * degrad - olon
        if theta > math.pi:
            theta -= 2.0 * math.pi
        if theta < -math.pi:
            theta += 2.0 * math.pi
        theta *= sn

        nx = int(ra * math.sin(theta) + LCC.xo + 0.5)
        ny = int(ro - ra * math.cos(theta) + LCC.yo + 0.5)

        return nx, ny

    @staticmethod
    def convert_to_latlon(nx: int, ny: int) -> tuple[float, float]:
        """격자좌표 → 위경도 변환 (역변환).

        Args:
            nx: 격자 X 좌표
            ny: 격자 Y 좌표

        Returns:
            (lat, lon) 위경도
        """
        degrad = math.pi / 180.0
        raddeg = 180.0 / math.pi

        re = LCC.re / LCC.grid
        slat1 = LCC.slat1 * degrad
        slat2 = LCC.slat2 * degrad
        olon = LCC.olon * degrad
        olat = LCC.olat * degrad

        sn = math.tan(math.pi * 0.25 + slat2 * 0.5) / math.tan(
            math.pi * 0.25 + slat1 * 0.5
        )
        sn = math.log(math.cos(slat1) / math.cos(slat2)) / math.log(sn)

        sf = math.tan(math.pi * 0.25 + slat1 * 0.5)
        sf = math.pow(sf, sn) * math.cos(slat1) / sn

        ro = math.tan(math.pi * 0.25 + olat * 0.5)
        ro = re * sf / math.pow(ro, sn)

        xn = nx - LCC.xo
        yn = ro - ny + LCC.yo

        ra = math.sqrt(xn * xn + yn * yn)
        if sn < 0:
            ra = -ra

        alat = math.pow(re * sf / ra, 1.0 / sn)
        alat = 2.0 * math.atan(alat) - math.pi * 0.5

        if abs(xn) <= 0.0:
            theta = 0.0
        elif abs(yn) <= 0.0:
            theta = math.pi * 0.5 if xn < 0 else -math.pi * 0.5
        else:
            theta = math.atan2(xn, yn)

        alon = theta / sn + olon
        lat = alat * raddeg
        lon = alon * raddeg

        return lat, lon

    @staticmethod
    def generate_weather_tip(
        weather: CurrentWeatherDTO | None,
        waste_category: str | None = None,
    ) -> str | None:
        """날씨 기반 분리배출 팁 생성.

        규칙:
        - 비/눈: 종이류 실내 보관 권장
        - 고온(25°C+): 음식물 빠른 배출 권장
        - 저온(0°C-): 액체류 동결 주의
        - 습도 높음(80%+): 건조 후 배출 권장

        Args:
            weather: 현재 날씨 정보
            waste_category: 폐기물 카테고리 (선택, 맞춤 팁용)

        Returns:
            날씨 기반 팁 문자열, 없으면 None
        """
        if weather is None:
            return None

        tips: list[str] = []

        # 강수 체크 (비/눈)
        if weather.precipitation_type == PrecipitationType.RAIN:
            tips.append("비 예보가 있어요. 종이류는 젖지 않게 보관 후 배출하세요.")
        elif weather.precipitation_type == PrecipitationType.SNOW:
            tips.append("눈 예보가 있어요. 배출 시 미끄럼 주의하세요.")
        elif weather.precipitation_type in (
            PrecipitationType.RAIN_SNOW,
            PrecipitationType.SHOWER,
        ):
            tips.append("강수 예보가 있어요. 종이류는 실내 보관 후 배출하세요.")

        # 기온 체크
        if weather.temperature >= 30:
            tips.append(
                f"기온이 {weather.temperature:.0f}°C로 높아요. "
                "음식물 쓰레기는 빨리 버리세요!"
            )
        elif weather.temperature >= 25:
            if waste_category and "음식물" in waste_category:
                tips.append(
                    f"기온이 {weather.temperature:.0f}°C예요. "
                    "음식물은 오래 두지 마세요."
                )
        elif weather.temperature <= 0:
            tips.append(
                f"기온이 {weather.temperature:.0f}°C로 영하예요. "
                "액체류 동결에 주의하세요."
            )

        # 습도 체크
        if weather.humidity >= 85:
            tips.append("습도가 높아요. 종이류는 건조 후 배출하세요.")

        return " ".join(tips) if tips else None

    @staticmethod
    def get_weather_emoji(weather: CurrentWeatherDTO | None) -> str:
        """날씨 이모지 반환.

        Args:
            weather: 현재 날씨 정보

        Returns:
            날씨에 맞는 이모지
        """
        if weather is None:
            return ""

        # 강수 우선
        if weather.precipitation_type == PrecipitationType.RAIN:
            return "🌧️"
        if weather.precipitation_type == PrecipitationType.SNOW:
            return "❄️"
        if weather.precipitation_type == PrecipitationType.RAIN_SNOW:
            return "🌨️"
        if weather.precipitation_type == PrecipitationType.SHOWER:
            return "🌦️"

        # 하늘 상태
        from chat_worker.application.ports.weather_client import SkyStatus

        if weather.sky_status == SkyStatus.CLEAR:
            if weather.temperature >= 25:
                return "☀️"
            return "🌤️"
        if weather.sky_status == SkyStatus.PARTLY_CLOUDY:
            return "⛅"
        if weather.sky_status == SkyStatus.CLOUDY:
            return "☁️"

        return ""


__all__ = [
    "WeatherService",
    "LccParameters",
    "LCC",
]
