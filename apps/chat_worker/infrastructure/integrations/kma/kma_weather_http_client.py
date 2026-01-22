"""KMA Weather HTTP Client - 기상청 단기예보 API Adapter.

Clean Architecture:
- Port: application/ports/weather_client.py
- Adapter: 이 파일 (HTTP 구현)

API 스펙:
- 엔드포인트: http://apis.data.go.kr/1360000/VilageFcstInfoService_2.0
- 인증: serviceKey 파라미터 (공공데이터포털 API 키)
- 응답: JSON

참고:
- https://www.data.go.kr/data/15084084/openapi.do
- https://apihub.kma.go.kr/
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

import httpx

from chat_worker.application.ports.weather_client import (
    CurrentWeatherDTO,
    PrecipitationType,
    SkyStatus,
    WeatherClientPort,
    WeatherForecastDTO,
    WeatherResponse,
)

logger = logging.getLogger(__name__)


class KmaWeatherHttpClient(WeatherClientPort):
    """기상청 단기예보 API HTTP 클라이언트.

    공공데이터포털 기상청 API 구현.

    Attributes:
        BASE_URL: API 기본 URL
        DEFAULT_TIMEOUT: 기본 타임아웃 (초)
    """

    BASE_URL = "http://apis.data.go.kr/1360000/VilageFcstInfoService_2.0"
    DEFAULT_TIMEOUT = 10.0

    def __init__(self, api_key: str, timeout: float = DEFAULT_TIMEOUT):
        """초기화.

        Args:
            api_key: 공공데이터포털 API 키 (Decoding 키 권장)
            timeout: HTTP 타임아웃 (초)
        """
        self._api_key = api_key
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """HTTP 클라이언트 lazy 초기화."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.BASE_URL,
                timeout=self._timeout,
            )
        return self._client

    def _get_base_datetime(self, now: datetime | None = None) -> tuple[str, str]:
        """API 요청용 base_date, base_time 계산.

        초단기실황은 매 정시 발표 (00, 01, ..., 23시).
        API는 발표 후 10분 정도 지나야 데이터 조회 가능.

        Args:
            now: 기준 시간 (기본: 현재 시간)

        Returns:
            (base_date, base_time) YYYYMMDD, HHMM 형식
        """
        if now is None:
            now = datetime.now()

        # 발표 시각: 정시 (API는 40분 이후 조회 가능)
        # 안전하게 1시간 전 데이터 사용
        if now.minute < 40:
            now = now - timedelta(hours=1)

        base_date = now.strftime("%Y%m%d")
        base_time = now.strftime("%H00")

        return base_date, base_time

    def _get_forecast_base_datetime(self, now: datetime | None = None) -> tuple[str, str]:
        """단기예보용 base_date, base_time 계산.

        단기예보는 02, 05, 08, 11, 14, 17, 20, 23시 발표.

        Args:
            now: 기준 시간

        Returns:
            (base_date, base_time) YYYYMMDD, HHMM 형식
        """
        if now is None:
            now = datetime.now()

        # 발표 시각 목록
        forecast_hours = [2, 5, 8, 11, 14, 17, 20, 23]

        # 현재 시간 이전의 가장 최근 발표 시각 찾기
        current_hour = now.hour
        base_hour = 23  # 기본값 (전날 23시)
        base_date = now

        for h in reversed(forecast_hours):
            if current_hour >= h + 1:  # 발표 후 1시간 여유
                base_hour = h
                break
        else:
            # 02시 이전이면 전날 23시 사용
            base_date = now - timedelta(days=1)
            base_hour = 23

        return base_date.strftime("%Y%m%d"), f"{base_hour:02d}00"

    def _parse_current_weather(self, data: dict[str, Any], nx: int, ny: int) -> WeatherResponse:
        """초단기실황 응답 파싱.

        Args:
            data: API 응답 JSON
            nx, ny: 요청한 격자 좌표

        Returns:
            WeatherResponse
        """
        try:
            response = data.get("response", {})
            header = response.get("header", {})
            result_code = header.get("resultCode", "")

            if result_code != "00":
                error_msg = header.get("resultMsg", "Unknown error")
                logger.warning(
                    "KMA API error response",
                    extra={"result_code": result_code, "error_msg": error_msg},
                )
                return WeatherResponse(
                    success=False,
                    error_message=f"KMA API: {error_msg} (code: {result_code})",
                    nx=nx,
                    ny=ny,
                )

            body = response.get("body", {})
            items = body.get("items", {}).get("item", [])

            # 카테고리별 값 추출
            values: dict[str, str] = {}
            for item in items:
                category = item.get("category", "")
                obs_value = item.get("obsrValue", "")
                values[category] = obs_value

            # DTO 생성
            current = CurrentWeatherDTO(
                temperature=float(values.get("T1H", "0")),
                precipitation=float(values.get("RN1", "0")),
                precipitation_type=PrecipitationType(int(values.get("PTY", "0"))),
                humidity=int(float(values.get("REH", "0"))),
                sky_status=SkyStatus(int(values.get("SKY", "1"))),
                wind_speed=float(values.get("WSD", "0")),
            )

            logger.debug(
                "KMA current weather parsed",
                extra={
                    "nx": nx,
                    "ny": ny,
                    "temperature": current.temperature,
                    "precipitation_type": current.precipitation_type.name,
                },
            )

            return WeatherResponse(
                success=True,
                current=current,
                nx=nx,
                ny=ny,
            )

        except (KeyError, ValueError, TypeError) as e:
            logger.error(
                "KMA response parsing error",
                extra={"error": str(e), "data_keys": list(data.keys())},
            )
            return WeatherResponse(
                success=False,
                error_message=f"Response parsing error: {e}",
                nx=nx,
                ny=ny,
            )

    def _parse_forecast(
        self, data: dict[str, Any], nx: int, ny: int, hours: int
    ) -> WeatherResponse:
        """단기예보 응답 파싱.

        Args:
            data: API 응답 JSON
            nx, ny: 격자 좌표
            hours: 조회 시간 범위

        Returns:
            WeatherResponse
        """
        try:
            response = data.get("response", {})
            header = response.get("header", {})
            result_code = header.get("resultCode", "")

            if result_code != "00":
                error_msg = header.get("resultMsg", "Unknown error")
                return WeatherResponse(
                    success=False,
                    error_message=f"KMA API: {error_msg}",
                    nx=nx,
                    ny=ny,
                )

            body = response.get("body", {})
            items = body.get("items", {}).get("item", [])

            # 시간대별로 그룹핑
            forecast_map: dict[str, dict[str, str]] = {}
            for item in items:
                fcst_date = item.get("fcstDate", "")
                fcst_time = item.get("fcstTime", "")
                category = item.get("category", "")
                fcst_value = item.get("fcstValue", "")

                key = f"{fcst_date}_{fcst_time}"
                if key not in forecast_map:
                    forecast_map[key] = {"date": fcst_date, "time": fcst_time}
                forecast_map[key][category] = fcst_value

            # DTO 리스트 생성
            forecasts: list[WeatherForecastDTO] = []
            now = datetime.now()
            cutoff = now + timedelta(hours=hours)

            for key in sorted(forecast_map.keys()):
                values = forecast_map[key]
                fcst_date = values["date"]
                fcst_time = values["time"]

                # 시간 범위 체크
                try:
                    fcst_dt = datetime.strptime(f"{fcst_date}{fcst_time}", "%Y%m%d%H%M")
                    if fcst_dt > cutoff:
                        continue
                except ValueError:
                    continue

                forecast = WeatherForecastDTO(
                    date=fcst_date,
                    time=fcst_time,
                    temperature=(float(values["TMP"]) if "TMP" in values else None),
                    precipitation_prob=int(float(values.get("POP", "0"))),
                    precipitation_type=PrecipitationType(int(values.get("PTY", "0"))),
                    sky_status=SkyStatus(int(values.get("SKY", "1"))),
                )
                forecasts.append(forecast)

            return WeatherResponse(
                success=True,
                forecasts=forecasts,
                nx=nx,
                ny=ny,
            )

        except (KeyError, ValueError, TypeError) as e:
            logger.error("KMA forecast parsing error", extra={"error": str(e)})
            return WeatherResponse(
                success=False,
                error_message=f"Forecast parsing error: {e}",
                nx=nx,
                ny=ny,
            )

    async def get_current_weather(self, nx: int, ny: int) -> WeatherResponse:
        """현재 날씨 조회 (초단기실황).

        Args:
            nx: 기상청 격자 X 좌표
            ny: 기상청 격자 Y 좌표

        Returns:
            WeatherResponse
        """
        client = await self._get_client()
        base_date, base_time = self._get_base_datetime()

        params = {
            "serviceKey": self._api_key,
            "pageNo": 1,
            "numOfRows": 10,
            "dataType": "JSON",
            "base_date": base_date,
            "base_time": base_time,
            "nx": nx,
            "ny": ny,
        }

        try:
            logger.debug(
                "KMA API request: getUltraSrtNcst",
                extra={
                    "nx": nx,
                    "ny": ny,
                    "base_date": base_date,
                    "base_time": base_time,
                },
            )

            response = await client.get("/getUltraSrtNcst", params=params)
            response.raise_for_status()
            data = response.json()
            return self._parse_current_weather(data, nx, ny)

        except httpx.HTTPStatusError as e:
            logger.error(
                "KMA API HTTP error",
                extra={
                    "status_code": e.response.status_code,
                    "detail": e.response.text[:200],
                },
            )
            return WeatherResponse(
                success=False,
                error_message=f"HTTP {e.response.status_code}",
                nx=nx,
                ny=ny,
            )
        except httpx.TimeoutException:
            logger.error("KMA API timeout", extra={"timeout": self._timeout})
            return WeatherResponse(
                success=False,
                error_message="Request timeout",
                nx=nx,
                ny=ny,
            )
        except Exception as e:
            logger.error("KMA API error", extra={"error": str(e)})
            return WeatherResponse(
                success=False,
                error_message=str(e),
                nx=nx,
                ny=ny,
            )

    async def get_forecast(self, nx: int, ny: int, hours: int = 24) -> WeatherResponse:
        """단기예보 조회.

        Args:
            nx: 기상청 격자 X 좌표
            ny: 기상청 격자 Y 좌표
            hours: 조회할 시간 범위

        Returns:
            WeatherResponse
        """
        client = await self._get_client()
        base_date, base_time = self._get_forecast_base_datetime()

        # 예보 데이터 양 계산 (시간당 약 12개 항목)
        num_of_rows = min(hours * 12, 1000)

        params = {
            "serviceKey": self._api_key,
            "pageNo": 1,
            "numOfRows": num_of_rows,
            "dataType": "JSON",
            "base_date": base_date,
            "base_time": base_time,
            "nx": nx,
            "ny": ny,
        }

        try:
            logger.debug(
                "KMA API request: getVilageFcst",
                extra={
                    "nx": nx,
                    "ny": ny,
                    "base_date": base_date,
                    "base_time": base_time,
                    "hours": hours,
                },
            )

            response = await client.get("/getVilageFcst", params=params)
            response.raise_for_status()
            data = response.json()
            return self._parse_forecast(data, nx, ny, hours)

        except httpx.HTTPStatusError as e:
            logger.error(
                "KMA API HTTP error (forecast)",
                extra={"status_code": e.response.status_code},
            )
            return WeatherResponse(
                success=False,
                error_message=f"HTTP {e.response.status_code}",
                nx=nx,
                ny=ny,
            )
        except httpx.TimeoutException:
            logger.error("KMA API timeout (forecast)")
            return WeatherResponse(
                success=False,
                error_message="Request timeout",
                nx=nx,
                ny=ny,
            )
        except Exception as e:
            logger.error("KMA API error (forecast)", extra={"error": str(e)})
            return WeatherResponse(
                success=False,
                error_message=str(e),
                nx=nx,
                ny=ny,
            )

    async def close(self) -> None:
        """HTTP 클라이언트 종료."""
        if self._client:
            await self._client.aclose()
            self._client = None
            logger.debug("KMA Weather HTTP client closed")


__all__ = ["KmaWeatherHttpClient"]
