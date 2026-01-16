"""WeatherService Unit Tests."""

import pytest

from chat_worker.application.ports.weather_client import (
    CurrentWeatherDTO,
    PrecipitationType,
    SkyStatus,
)
from chat_worker.application.services.weather_service import (
    LCC,
    WeatherService,
)


class TestWeatherServiceGridConversion:
    """격자좌표 변환 테스트."""

    def test_convert_to_grid_seoul(self) -> None:
        """서울 시청 좌표 변환."""
        # 서울 시청: 위도 37.5665, 경도 126.9780
        nx, ny = WeatherService.convert_to_grid(37.5665, 126.9780)

        # 기상청 기준 서울 시청은 (60, 127) 근처
        assert 58 <= nx <= 62
        assert 125 <= ny <= 129

    def test_convert_to_grid_busan(self) -> None:
        """부산 좌표 변환."""
        # 부산시청: 위도 35.1796, 경도 129.0756
        nx, ny = WeatherService.convert_to_grid(35.1796, 129.0756)

        # 부산은 (98, 76) 근처
        assert 96 <= nx <= 100
        assert 74 <= ny <= 78

    def test_convert_to_grid_jeju(self) -> None:
        """제주 좌표 변환."""
        # 제주시: 위도 33.4996, 경도 126.5312
        nx, ny = WeatherService.convert_to_grid(33.4996, 126.5312)

        # 제주는 (53, 38) 근처
        assert 51 <= nx <= 55
        assert 36 <= ny <= 40

    def test_convert_to_latlon_roundtrip(self) -> None:
        """좌표 변환 왕복 테스트."""
        original_lat, original_lon = 37.5665, 126.9780

        nx, ny = WeatherService.convert_to_grid(original_lat, original_lon)
        lat, lon = WeatherService.convert_to_latlon(nx, ny)

        # 왕복 변환 후 오차 0.1도 이내
        assert abs(lat - original_lat) < 0.1
        assert abs(lon - original_lon) < 0.1


class TestWeatherServiceTipGeneration:
    """날씨 기반 팁 생성 테스트."""

    def test_generate_weather_tip_none_weather(self) -> None:
        """날씨 정보 없으면 None."""
        result = WeatherService.generate_weather_tip(None)
        assert result is None

    def test_generate_weather_tip_rain(self) -> None:
        """비 예보 시 종이류 팁."""
        weather = CurrentWeatherDTO(
            temperature=20.0,
            humidity=70,
            sky_status=SkyStatus.CLOUDY,
            precipitation_type=PrecipitationType.RAIN,
            precipitation=5.0,
        )

        result = WeatherService.generate_weather_tip(weather)

        assert result is not None
        assert "비" in result
        assert "종이류" in result

    def test_generate_weather_tip_snow(self) -> None:
        """눈 예보 시 미끄럼 주의 팁."""
        weather = CurrentWeatherDTO(
            temperature=-5.0,
            humidity=60,
            sky_status=SkyStatus.CLOUDY,
            precipitation_type=PrecipitationType.SNOW,
            precipitation=3.0,
        )

        result = WeatherService.generate_weather_tip(weather)

        assert result is not None
        assert "눈" in result
        assert "미끄럼" in result

    def test_generate_weather_tip_high_temperature(self) -> None:
        """고온 시 음식물 팁."""
        weather = CurrentWeatherDTO(
            temperature=32.0,
            humidity=60,
            sky_status=SkyStatus.CLEAR,
            precipitation_type=PrecipitationType.NONE,
            precipitation=0.0,
        )

        result = WeatherService.generate_weather_tip(weather)

        assert result is not None
        assert "음식물" in result
        assert "빨리" in result

    def test_generate_weather_tip_freezing(self) -> None:
        """영하 시 동결 주의 팁."""
        weather = CurrentWeatherDTO(
            temperature=-3.0,
            humidity=50,
            sky_status=SkyStatus.CLEAR,
            precipitation_type=PrecipitationType.NONE,
            precipitation=0.0,
        )

        result = WeatherService.generate_weather_tip(weather)

        assert result is not None
        assert "영하" in result
        assert "동결" in result

    def test_generate_weather_tip_high_humidity(self) -> None:
        """고습도 시 건조 팁."""
        weather = CurrentWeatherDTO(
            temperature=20.0,
            humidity=90,
            sky_status=SkyStatus.CLOUDY,
            precipitation_type=PrecipitationType.NONE,
            precipitation=0.0,
        )

        result = WeatherService.generate_weather_tip(weather)

        assert result is not None
        assert "습도" in result
        assert "건조" in result

    def test_generate_weather_tip_normal_weather(self) -> None:
        """정상 날씨면 팁 없음."""
        weather = CurrentWeatherDTO(
            temperature=22.0,
            humidity=55,
            sky_status=SkyStatus.CLEAR,
            precipitation_type=PrecipitationType.NONE,
            precipitation=0.0,
        )

        result = WeatherService.generate_weather_tip(weather)

        assert result is None

    def test_generate_weather_tip_with_waste_category(self) -> None:
        """폐기물 카테고리에 따른 맞춤 팁."""
        weather = CurrentWeatherDTO(
            temperature=26.0,
            humidity=60,
            sky_status=SkyStatus.CLEAR,
            precipitation_type=PrecipitationType.NONE,
            precipitation=0.0,
        )

        # 음식물 관련 카테고리일 때만 25도에서도 팁 제공
        result = WeatherService.generate_weather_tip(weather, "음식물 쓰레기")

        assert result is not None
        assert "음식물" in result


class TestWeatherServiceEmoji:
    """날씨 이모지 테스트."""

    def test_get_weather_emoji_none(self) -> None:
        """날씨 없으면 빈 문자열."""
        assert WeatherService.get_weather_emoji(None) == ""

    def test_get_weather_emoji_rain(self) -> None:
        """비 이모지."""
        weather = CurrentWeatherDTO(
            temperature=20.0,
            humidity=80,
            sky_status=SkyStatus.CLOUDY,
            precipitation_type=PrecipitationType.RAIN,
            precipitation=10.0,
        )

        assert WeatherService.get_weather_emoji(weather) == "🌧️"

    def test_get_weather_emoji_snow(self) -> None:
        """눈 이모지."""
        weather = CurrentWeatherDTO(
            temperature=-5.0,
            humidity=70,
            sky_status=SkyStatus.CLOUDY,
            precipitation_type=PrecipitationType.SNOW,
            precipitation=5.0,
        )

        assert WeatherService.get_weather_emoji(weather) == "❄️"

    def test_get_weather_emoji_hot_sunny(self) -> None:
        """더운 맑은 날 이모지."""
        weather = CurrentWeatherDTO(
            temperature=30.0,
            humidity=60,
            sky_status=SkyStatus.CLEAR,
            precipitation_type=PrecipitationType.NONE,
            precipitation=0.0,
        )

        assert WeatherService.get_weather_emoji(weather) == "☀️"

    def test_get_weather_emoji_cloudy(self) -> None:
        """흐림 이모지."""
        weather = CurrentWeatherDTO(
            temperature=20.0,
            humidity=60,
            sky_status=SkyStatus.CLOUDY,
            precipitation_type=PrecipitationType.NONE,
            precipitation=0.0,
        )

        assert WeatherService.get_weather_emoji(weather) == "☁️"


class TestLccParameters:
    """LCC 파라미터 테스트."""

    def test_lcc_parameters_values(self) -> None:
        """LCC 파라미터 기본값 확인."""
        assert LCC.re == 6371.00877
        assert LCC.grid == 5.0
        assert LCC.xo == 43
        assert LCC.yo == 136
