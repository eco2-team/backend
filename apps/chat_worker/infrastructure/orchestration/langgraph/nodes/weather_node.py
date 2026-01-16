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

사용 시나리오:
1. 분리배출 답변에 날씨 기반 팁 추가
2. 비/눈 예보 시 종이류 실내보관 권장
3. 고온 시 음식물 빠른 배출 권장

Flow:
    Router → weather (병렬) → Answer
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from chat_worker.application.commands.get_weather_command import (
    GetWeatherCommand,
    GetWeatherInput,
)
from chat_worker.infrastructure.orchestration.langgraph.nodes.node_executor import (
    NodeExecutor,
)

if TYPE_CHECKING:
    from chat_worker.application.ports.events import ProgressNotifierPort
    from chat_worker.application.ports.weather_client import WeatherClientPort

logger = logging.getLogger(__name__)


def create_weather_node(
    weather_client: "WeatherClientPort",
    event_publisher: "ProgressNotifierPort",
):
    """날씨 노드 팩토리.

    Node는 LangGraph 어댑터:
    - state → input DTO 변환
    - Command(UseCase) 호출
    - output → state 변환
    - progress notify (UX)

    Args:
        weather_client: 날씨 클라이언트
        event_publisher: 이벤트 발행기

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
            message="🌤️ 날씨 정보 확인 중...",
        )

        # 1. state → input DTO 변환
        # user_location에서 위경도 추출
        user_location = state.get("user_location")
        lat: float | None = None
        lon: float | None = None

        if isinstance(user_location, dict):
            lat = user_location.get("lat") or user_location.get("latitude")
            lon = user_location.get("lon") or user_location.get("longitude")

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
                **state,
                "weather_context": None,
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
                **state,
                "weather_context": None,
            }

        # Progress: 완료 (UX)
        context = output.weather_context or {}
        has_tip = bool(context.get("tip"))

        await event_publisher.notify_stage(
            task_id=job_id,
            stage="weather",
            status="completed",
            progress=45,
            result={
                "temperature": context.get("temperature"),
                "has_tip": has_tip,
            },
            message=f"{context.get('emoji', '')} 날씨 확인 완료",
        )

        return {
            **state,
            "weather_context": output.weather_context,
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
