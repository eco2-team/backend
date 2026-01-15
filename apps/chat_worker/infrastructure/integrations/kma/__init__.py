"""KMA (기상청) Integration - 단기예보 API 클라이언트.

기상청 공공데이터포털 API:
- 초단기실황 (getUltraSrtNcst): 현재 날씨
- 단기예보 (getVilageFcst): 향후 예보

참고:
- https://www.data.go.kr/data/15084084/openapi.do
"""

from chat_worker.infrastructure.integrations.kma.kma_weather_http_client import (
    KmaWeatherHttpClient,
)

__all__ = ["KmaWeatherHttpClient"]
