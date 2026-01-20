"""Weather Node - LangGraph 어댑터.

얇은 어댑터: state 변환 + Command 호출 + progress notify (UX).
정책/흐름은 GetWeatherCommand(Application)에서 처리.

Clean Architecture:
- Node(Adapter): 이 파일 - LangGraph glue code
- Command(UseCase): GetWeatherCommand - 정책/흐름
- Service: WeatherService - 순수 비즈니스 로직

Production Architecture:
- NodeExecutor로 Policy 적용 (timeout, retry, circuit breaker)
- weather 노드는 FAIL_OPEN (보조 정보, 없어도 답변 가능)

Channel Separation:
- 출력 채널: weather_context
- Reducer: priority_preemptive_reducer
- spread 금지: {"weather_context": create_context(...)} 형태로 반환

사용 시나리오:
1. 분리배출 답변에 날씨 기반 팁 추가
2. 비/눈 예보 시 종이류 실내보관 권장
3. 고온 시 음식물 빠른 배출 권장
4. 직접 날씨 질문 시 (WEATHER intent) 날씨 정보 제공

Geocoding 지원:
- GPS 좌표 없을 시 메시지에서 장소명 추출
- Kakao Local API로 장소명 → 좌표 변환 (geocoding)
- 예: "강남역 날씨" → Kakao API → (127.02, 37.50) → KMA API

Flow:
    Router → weather (병렬) → Answer
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Any

from chat_worker.application.commands.get_weather_command import (
    GetWeatherCommand,
    GetWeatherInput,
)
from chat_worker.infrastructure.orchestration.langgraph.context_helper import (
    create_context,
    create_error_context,
)
from chat_worker.infrastructure.orchestration.langgraph.nodes.node_executor import (
    NodeExecutor,
)

if TYPE_CHECKING:
    from chat_worker.application.ports.events import ProgressNotifierPort
    from chat_worker.application.ports.kakao_local_client import KakaoLocalClientPort
    from chat_worker.application.ports.weather_client import WeatherClientPort

logger = logging.getLogger(__name__)

# 위치 추출 패턴 (한국 지명)
LOCATION_PATTERNS = [
    # "강남역 날씨", "서울 날씨", "부산 날씨"
    r"([가-힣]+(?:역|동|구|시|군|읍|면|리|로|길))\s*(?:근처|주변)?\s*날씨",
    # "강남 날씨", "홍대 날씨"
    r"([가-힣]{2,10})\s+날씨",
    # "날씨 강남", "날씨 서울"
    r"날씨\s+([가-힣]{2,10})",
    # "강남역 9번 출구", "홍대입구역 2번 출구"
    r"([가-힣]+역)\s*\d*번?\s*출구",
]


def extract_location_from_message(message: str) -> str | None:
    """메시지에서 장소명을 추출합니다.

    Args:
        message: 사용자 메시지

    Returns:
        추출된 장소명 또는 None
    """
    for pattern in LOCATION_PATTERNS:
        match = re.search(pattern, message)
        if match:
            location = match.group(1)
            logger.debug(f"Location extracted from message: {location}")
            return location
    return None


async def geocode_location(
    kakao_client: "KakaoLocalClientPort",
    place_name: str,
) -> tuple[float, float] | None:
    """장소명을 좌표로 변환합니다 (Geocoding).

    Args:
        kakao_client: Kakao Local API 클라이언트
        place_name: 장소명 (예: "강남역")

    Returns:
        (longitude, latitude) 튜플 또는 None
    """
    try:
        response = await kakao_client.search_keyword(place_name, size=1)
        if response.places:
            place = response.places[0]
            # Kakao API는 x=경도, y=위도 반환
            lon = float(place.x)
            lat = float(place.y)
            logger.info(
                "Geocoding successful",
                extra={
                    "place_name": place_name,
                    "result": place.place_name,
                    "lat": lat,
                    "lon": lon,
                },
            )
            return lon, lat
    except Exception as e:
        logger.warning(f"Geocoding failed for '{place_name}': {e}")
    return None


def create_weather_node(
    weather_client: "WeatherClientPort",
    event_publisher: "ProgressNotifierPort",
    kakao_client: "KakaoLocalClientPort | None" = None,
):
    """날씨 노드 팩토리.

    Node는 LangGraph 어댑터:
    - state → input DTO 변환
    - Command(UseCase) 호출
    - output → state 변환
    - progress notify (UX)

    Geocoding 지원:
    - kakao_client가 제공되면 메시지에서 장소명을 추출하여 좌표 변환
    - GPS 좌표가 없을 때만 geocoding 시도

    Args:
        weather_client: 날씨 클라이언트
        event_publisher: 이벤트 발행기
        kakao_client: Kakao Local API 클라이언트 (geocoding용, 선택)

    Returns:
        weather_node 함수
    """
    # Command(UseCase) 인스턴스 생성 - Port 조립
    command = GetWeatherCommand(weather_client=weather_client)

    async def _weather_node_inner(state: dict[str, Any]) -> dict[str, Any]:
        """실제 노드 로직 (NodeExecutor가 래핑).

        역할:
        1. state에서 값 추출 (LangGraph glue)
        2. Command 호출 (정책/흐름 위임)
        3. output → state 변환
        4. progress notify (UX)

        Args:
            state: 현재 LangGraph 상태

        Returns:
            업데이트된 상태
        """
        job_id = state.get("job_id", "")

        # Progress: 시작 (UX) - 조용하게 (보조 정보)
        await event_publisher.notify_stage(
            task_id=job_id,
            stage="weather",
            status="started",
            progress=40,
            message="날씨 정보 확인 중",
        )

        # 1. state → input DTO 변환
        # user_location에서 위경도 추출
        user_location = state.get("user_location")
        lat: float | None = None
        lon: float | None = None
        geocoded_place: str | None = None

        if isinstance(user_location, dict):
            lat = user_location.get("lat") or user_location.get("latitude")
            lon = user_location.get("lon") or user_location.get("longitude")

        # GPS 좌표가 없으면 메시지에서 장소명 추출 후 geocoding 시도
        if (lat is None or lon is None) and kakao_client is not None:
            message = state.get("message", "")
            place_name = extract_location_from_message(message)

            if place_name:
                logger.info(
                    "Attempting geocoding for weather",
                    extra={"job_id": job_id, "place_name": place_name},
                )
                coords = await geocode_location(kakao_client, place_name)
                if coords:
                    lon, lat = coords
                    geocoded_place = place_name
                    logger.info(
                        "Geocoding successful for weather",
                        extra={
                            "job_id": job_id,
                            "place_name": place_name,
                            "lat": lat,
                            "lon": lon,
                        },
                    )

        # 분류 결과에서 폐기물 카테고리 추출 (맞춤 팁용)
        classification = state.get("classification_result")
        waste_category = None
        if isinstance(classification, dict):
            waste_category = classification.get("category")

        input_dto = GetWeatherInput(
            job_id=job_id,
            lat=lat,
            lon=lon,
            waste_category=waste_category,
        )

        # 2. Command 실행 (정책/흐름은 Command에서)
        output = await command.execute(input_dto)

        # 3. output → state 변환
        if output.needs_location:
            # 위치 없으면 조용히 스킵 (날씨는 필수 아님)
            logger.debug(
                "Weather skipped - no location",
                extra={"job_id": job_id},
            )
            await event_publisher.notify_stage(
                task_id=job_id,
                stage="weather",
                status="skipped",
                message="위치 정보 없음",
            )
            return {
                "weather_context": create_error_context(
                    producer="weather",
                    job_id=job_id,
                    error="위치 정보 없음",
                ),
            }

        if not output.success:
            logger.warning(
                "Weather fetch failed",
                extra={
                    "job_id": job_id,
                    "error": output.error_message,
                },
            )
            await event_publisher.notify_stage(
                task_id=job_id,
                stage="weather",
                status="failed",
                result={"error": output.error_message},
            )
            return {
                "weather_context": create_error_context(
                    producer="weather",
                    job_id=job_id,
                    error=output.error_message or "날씨 조회 실패",
                ),
            }

        # Progress: 완료 (UX)
        context = output.weather_context or {}
        has_tip = bool(context.get("tip"))

        # geocoding된 장소명을 context에 추가
        if geocoded_place:
            context["location_name"] = geocoded_place

        temp = context.get("temperature")
        location_msg = f" ({geocoded_place})" if geocoded_place else ""
        await event_publisher.notify_stage(
            task_id=job_id,
            stage="weather",
            status="completed",
            progress=45,
            result={
                "temperature": temp,
                "has_tip": has_tip,
                "location_name": geocoded_place,
            },
            message=f"날씨 확인 완료{location_msg}: {temp}도" if temp else "날씨 확인 완료",
        )

        return {
            "weather_context": create_context(
                data=context,
                producer="weather",
                job_id=job_id,
            ),
        }

    # NodeExecutor로 래핑 (Policy 적용: timeout, retry, circuit breaker)
    executor = NodeExecutor.get_instance()

    async def weather_node(state: dict[str, Any]) -> dict[str, Any]:
        """LangGraph 노드 (Policy 적용됨).

        NodeExecutor가 다음을 처리:
        - Circuit Breaker 확인
        - Timeout 적용 (5000ms)
        - Retry (1회)
        - FAIL_OPEN 처리 (실패해도 진행)
        """
        return await executor.execute(
            node_name="weather",
            node_func=_weather_node_inner,
            state=state,
        )

    return weather_node


__all__ = ["create_weather_node"]
