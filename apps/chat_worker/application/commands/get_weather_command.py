"""Get Weather Command.

날씨 정보 조회 UseCase.

Clean Architecture:
- Command(UseCase): 이 파일 - Port 호출, 오케스트레이션
- Service: WeatherService - 순수 비즈니스 로직 (좌표변환, 팁생성)
- Port: WeatherClientPort - HTTP API 호출
- Node(Adapter): weather_node.py - LangGraph glue

사용 시나리오:
1. 분리배출 팁에 날씨 컨텍스트 추가 (비오면 종이 실내보관 등)
2. 날씨 기반 배출 권장사항 제공
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from chat_worker.application.services.weather_service import WeatherService

if TYPE_CHECKING:
    from chat_worker.application.ports.weather_client import WeatherClientPort

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GetWeatherInput:
    """Command 입력 DTO.

    Attributes:
        job_id: 작업 ID (로깅/추적용)
        lat: 위도 (user_location에서 추출)
        lon: 경도 (user_location에서 추출)
        waste_category: 폐기물 카테고리 (맞춤 팁용)
    """

    job_id: str
    lat: float | None = None
    lon: float | None = None
    waste_category: str | None = None


@dataclass
class GetWeatherOutput:
    """Command 출력 DTO.

    Attributes:
        success: 성공 여부
        weather_context: 날씨 컨텍스트 (answer에 주입)
        needs_location: 위치 정보 필요 여부
        error_message: 에러 메시지
        events: 발생한 이벤트 목록
    """

    success: bool
    weather_context: dict[str, Any] | None = None
    needs_location: bool = False
    error_message: str | None = None
    events: list[str] = field(default_factory=list)


class GetWeatherCommand:
    """날씨 정보 조회 Command (UseCase).

    Port 호출 + 오케스트레이션:
    1. 위경도 → 격자좌표 변환 (Service - 순수 로직)
    2. API 호출 (WeatherClientPort)
    3. 날씨 팁 생성 (Service - 순수 로직)

    Usage:
        command = GetWeatherCommand(weather_client=client)
        output = await command.execute(input_dto)
    """

    def __init__(
        self,
        weather_client: "WeatherClientPort",
    ) -> None:
        """초기화.

        Args:
            weather_client: 날씨 클라이언트 (Port)
        """
        self._weather_client = weather_client

    async def execute(self, input_dto: GetWeatherInput) -> GetWeatherOutput:
        """Command 실행.

        Args:
            input_dto: 입력 DTO

        Returns:
            GetWeatherOutput
        """
        events: list[str] = []

        # 1. 좌표 확인
        if input_dto.lat is None or input_dto.lon is None:
            events.append("location_required")
            return GetWeatherOutput(
                success=True,
                weather_context={"type": "no_location", "context": None},
                needs_location=True,
                events=events,
            )

        # 2. 위경도 → 격자좌표 변환 (Service - 순수 로직)
        try:
            nx, ny = WeatherService.convert_to_grid(input_dto.lat, input_dto.lon)
            events.append("grid_converted")
            logger.debug(
                "Grid coordinates calculated",
                extra={
                    "job_id": input_dto.job_id,
                    "lat": input_dto.lat,
                    "lon": input_dto.lon,
                    "nx": nx,
                    "ny": ny,
                },
            )
        except Exception as e:
            logger.error(
                "Grid conversion failed",
                extra={"job_id": input_dto.job_id, "error": str(e)},
            )
            events.append("grid_conversion_error")
            return GetWeatherOutput(
                success=False,
                weather_context={"type": "error", "context": None},
                error_message=f"좌표 변환 실패: {e}",
                events=events,
            )

        # 3. API 호출 (Port)
        try:
            response = await self._weather_client.get_current_weather(nx, ny)
            events.append("weather_fetched")

            if not response.success:
                events.append("weather_api_failed")
                return GetWeatherOutput(
                    success=False,
                    weather_context={"type": "error", "context": None},
                    error_message=response.error_message,
                    events=events,
                )

            logger.info(
                "Weather fetched successfully",
                extra={
                    "job_id": input_dto.job_id,
                    "nx": nx,
                    "ny": ny,
                    "temperature": response.current.temperature if response.current else None,
                },
            )

        except Exception as e:
            logger.error(
                "Weather API error",
                extra={"job_id": input_dto.job_id, "error": str(e)},
            )
            events.append("weather_api_error")
            return GetWeatherOutput(
                success=False,
                weather_context={"type": "error", "context": None},
                error_message=str(e),
                events=events,
            )

        # 4. 날씨 팁 생성 (Service - 순수 로직)
        tip = WeatherService.generate_weather_tip(
            response.current,
            input_dto.waste_category,
        )
        emoji = WeatherService.get_weather_emoji(response.current)

        # 5. 컨텍스트 생성
        context: dict[str, Any] = {
            "type": "weather",
            "temperature": response.current.temperature if response.current else None,
            "humidity": response.current.humidity if response.current else None,
            "precipitation_type": (
                response.current.precipitation_type.name
                if response.current
                else None
            ),
            "tip": tip,
            "emoji": emoji,
            "context": self._build_context_string(response.current, tip, emoji),
        }

        events.append("context_built")

        return GetWeatherOutput(
            success=True,
            weather_context=context,
            events=events,
        )

    def _build_context_string(
        self,
        weather,
        tip: str | None,
        emoji: str,
    ) -> str | None:
        """Answer에 주입할 컨텍스트 문자열 생성."""
        if weather is None:
            return None

        parts = []

        # 현재 날씨 정보
        parts.append(f"{emoji} 현재 기온 {weather.temperature:.0f}°C")

        if weather.humidity >= 70:
            parts.append(f"습도 {weather.humidity}%")

        # 날씨 팁
        if tip:
            parts.append(tip)

        return ", ".join(parts) if parts else None


__all__ = [
    "GetWeatherCommand",
    "GetWeatherInput",
    "GetWeatherOutput",
]
