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

Function Calling:
- LLM이 날씨 정보 필요 여부를 동적으로 판단
- 분리배출 시기, 보관 방법 등의 질문에만 날씨 API 호출
- 불필요한 API 호출 감소로 비용 절감

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
    Router → weather (Function Calling) → [API 실행 or Skip] → Answer
"""

from __future__ import annotations

import logging
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
    from chat_worker.application.ports.llm import LLMClientPort
    from chat_worker.application.ports.weather_client import WeatherClientPort

logger = logging.getLogger(__name__)

# Function Definition for OpenAI Function Calling
WEATHER_FUNCTION = {
    "name": "get_weather",
    "description": "현재 날씨 정보를 조회하고 분리배출 관련 팁을 제공합니다.",
    "parameters": {
        "type": "object",
        "properties": {
            "needs_weather": {
                "type": "boolean",
                "description": "날씨 정보가 답변에 필요한지 여부. 분리배출 시기, 보관 방법 등의 질문에 true",
            },
            "waste_category": {
                "type": "string",
                "description": "폐기물 카테고리 (예: '종이류', '음식물', '플라스틱'). 맞춤 팁 생성용",
            },
        },
        "required": ["needs_weather"],
    },
}


def create_weather_node(
    weather_client: "WeatherClientPort",
    event_publisher: "ProgressNotifierPort",
    llm: "LLMClientPort",
):
    """날씨 노드 팩토리.

    Node는 LangGraph 어댑터:
    - state → input DTO 변환
    - LLM Function Calling으로 필요 여부 판단
    - Command(UseCase) 호출
    - output → state 변환
    - progress notify (UX)

    Geocoding 지원:
    - kakao_client가 제공되면 메시지에서 장소명을 추출하여 좌표 변환
    - GPS 좌표가 없을 때만 geocoding 시도

    Args:
        weather_client: 날씨 클라이언트
        event_publisher: 이벤트 발행기
        llm: LLM 클라이언트 (Function Calling용)

    Returns:
        weather_node 함수
    """
    # Command(UseCase) 인스턴스 생성 - Port 조립
    command = GetWeatherCommand(weather_client=weather_client)

    async def _weather_node_inner(state: dict[str, Any]) -> dict[str, Any]:
        """실제 노드 로직 (NodeExecutor가 래핑).

        역할:
        1. state에서 값 추출 (LangGraph glue)
        2. LLM Function Calling으로 필요 여부 판단
        3. Command 호출 (정책/흐름 위임)
        4. output → state 변환
        5. progress notify (UX)

        Args:
            state: 현재 LangGraph 상태

        Returns:
            업데이트된 상태
        """
        job_id = state.get("job_id", "")
        message = state.get("message", "")

        # Progress: 시작 (UX) - 조용하게 (보조 정보)
        await event_publisher.notify_stage(
            task_id=job_id,
            stage="weather",
            status="started",
            progress=40,
            message="날씨 정보 필요 여부 확인 중",
        )

        # 1. LLM Function Calling으로 날씨 정보 필요 여부 판단
        system_prompt = """사용자 질문에 날씨 정보가 필요한지 판단하세요.

날씨 정보가 필요한 경우 (needs_weather=true):
- "언제 버리는 게 좋아?" → 비 예보 확인 필요
- "종이는 어떻게 보관?" → 습도/강수 확인 필요
- "음식물 쓰레기 냄새" → 온도 확인 필요
- "비 오는데 종이 버려도 돼?" → 날씨 기반 조언 필요

날씨 정보가 불필요한 경우 (needs_weather=false):
- "페트병 분리배출 방법" → 날씨 무관
- "캐릭터 소개" → 날씨 무관
- "재활용 마크 종류" → 날씨 무관
"""

        try:
            func_name, func_args = await llm.generate_function_call(
                prompt=message,
                functions=[WEATHER_FUNCTION],
                system_prompt=system_prompt,
                function_call={"name": "get_weather"},  # 강제 호출
            )

            if not func_args or not func_args.get("needs_weather"):
                # 날씨 불필요 → 스킵
                logger.debug(
                    "Weather not needed for this query",
                    extra={"job_id": job_id, "user_message": message},
                )
                await event_publisher.notify_stage(
                    task_id=job_id,
                    stage="weather",
                    status="skipped",
                    message="날씨 정보 불필요",
                )
                return {
                    "weather_context": create_context(
                        data={"skipped": True, "reason": "날씨 정보 불필요"},
                        producer="weather",
                        job_id=job_id,
                    ),
                }

        except Exception as e:
            # LLM 호출 실패 → fallback: 날씨 조회 시도
            logger.warning(
                f"Function calling failed, proceeding with weather fetch: {e}",
                extra={"job_id": job_id},
            )
            func_args = {"needs_weather": True, "waste_category": None}

        # 2. state → input DTO 변환
        # user_location에서 위경도 추출
        user_location = state.get("user_location")
        lat: float | None = None
        lon: float | None = None
        geocoded_place: str | None = None

        if isinstance(user_location, dict):
            lat = user_location.get("lat") or user_location.get("latitude")
            lon = user_location.get("lon") or user_location.get("longitude")

        # Function call 결과에서 waste_category 추출 (우선순위)
        # 없으면 분류 결과에서 추출
        waste_category = func_args.get("waste_category")
        if not waste_category:
            classification = state.get("classification_result")
            if isinstance(classification, dict):
                waste_category = classification.get("category")

        input_dto = GetWeatherInput(
            job_id=job_id,
            lat=lat,
            lon=lon,
            waste_category=waste_category,
        )

        # 3. Command 실행 (정책/흐름은 Command에서)
        output = await command.execute(input_dto)

        # 4. output → state 변환
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
