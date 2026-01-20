"""Weather Agent Node - LLM with Weather/Geocoding Tools.

LLM이 날씨 API와 Geocoding API를 Tool로 사용하여 날씨 정보를 제공하는 에이전트 노드.

Architecture:
- LLM이 사용자 메시지를 분석하여 적절한 Tool 선택
- Tool 실행 결과를 LLM이 해석하여 자연어 응답 생성
- OpenAI/Gemini 모두 지원 (Function Calling)

Tools:
- get_weather: 좌표 기반 날씨 조회
- geocode: 장소명을 좌표로 변환

Flow:
    Router → weather_agent → Answer
             └─ LLM analyzes message
             └─ LLM calls tools (Weather/Kakao API)
             └─ LLM generates weather summary with tips
             └─ Returns weather_context
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any

from chat_worker.application.services.weather_service import WeatherService
from chat_worker.infrastructure.orchestration.langgraph.context_helper import (
    create_context,
    create_error_context,
)

if TYPE_CHECKING:
    from chat_worker.application.ports.events import ProgressNotifierPort
    from chat_worker.application.ports.kakao_local_client import KakaoLocalClientPort
    from chat_worker.application.ports.weather_client import WeatherClientPort

logger = logging.getLogger(__name__)


# ============================================================
# Tool Definitions
# ============================================================


class ToolName(str, Enum):
    """사용 가능한 Tool 이름."""

    GET_WEATHER = "get_weather"
    GEOCODE = "geocode"


# ============================================================
# OpenAI Function Calling Tools (GPT-5.2 Strict Mode)
# ============================================================
# Best Practices Applied (2026):
# 1. Prescriptive descriptions (WHEN to use, not just what)
# 2. Front-load key rules and requirements
# 3. Include usage criteria and edge cases
# 4. Strict mode enabled for schema validation (GPT-5.2 필수 권장)
# Reference: https://cookbook.openai.com/examples/gpt-5/gpt-5-1_prompting_guide

OPENAI_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": (
                "좌표 기반 현재 날씨 조회. "
                "사용 시점: 사용자가 날씨 정보를 요청하고 좌표가 있을 때 호출. "
                "반환값: 기온, 습도, 강수형태, 날씨 팁 포함. "
                "주의: 좌표 없이 호출 불가. 사용자가 '강남역 날씨'라고 하면 "
                "먼저 geocode로 '강남역' 좌표를 얻은 후 이 함수 호출. "
                "사용자 위치(user_location)가 이미 있으면 바로 호출 가능."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "latitude": {
                        "type": "number",
                        "description": "위도. 필수. 범위: 33.0~43.0 (한국)",
                    },
                    "longitude": {
                        "type": "number",
                        "description": "경도. 필수. 범위: 124.0~132.0 (한국)",
                    },
                    "waste_category": {
                        "type": "string",
                        "description": (
                            "폐기물 카테고리 (날씨 팁 맞춤용, 선택). "
                            "예: 'paper', 'plastic', 'food', 'general'. "
                            "분리배출 관련 질문이면 해당 카테고리 전달."
                        ),
                    },
                },
                "required": ["latitude", "longitude"],
                "additionalProperties": False,
            },
            "strict": True,
        },
    },
    {
        "type": "function",
        "function": {
            "name": "geocode",
            "description": (
                "장소명/주소를 좌표(위도, 경도)로 변환. "
                "사용 시점: 사용자가 '강남역 날씨', '서울 날씨' 등 "
                "특정 지역을 언급했으나 좌표가 없을 때 먼저 호출. "
                "실행 순서: 이 함수로 좌표를 먼저 얻은 후 get_weather 호출. "
                "주의: 사용자 위치(user_location)가 이미 있으면 호출 불필요."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "place_name": {
                        "type": "string",
                        "description": (
                            "좌표로 변환할 장소명 또는 주소. "
                            "예: '강남역', '홍대입구역', '서울시 강남구', '부산 해운대'. "
                            "가능한 구체적으로 입력."
                        ),
                    },
                },
                "required": ["place_name"],
                "additionalProperties": False,
            },
            "strict": True,
        },
    },
]

# ============================================================
# Gemini Function Calling Tools (Gemini 3)
# ============================================================
# Best Practices Applied (2026):
# 1. Clear, prescriptive descriptions
# 2. Strong-typed parameters
# 3. Parallel & Compositional function calling 지원
# Reference: https://ai.google.dev/gemini-api/docs/function-calling

GEMINI_TOOLS = [
    {
        "name": "get_weather",
        "description": (
            "좌표 기반 현재 날씨 조회. "
            "사용 시점: 사용자가 날씨 정보를 요청하고 좌표가 있을 때 호출. "
            "반환값: 기온, 습도, 강수형태, 날씨 팁 포함. "
            "주의: 좌표 없이 호출 불가. 사용자가 '강남역 날씨'라고 하면 "
            "먼저 geocode로 '강남역' 좌표를 얻은 후 이 함수 호출."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "latitude": {
                    "type": "number",
                    "description": "위도. 필수. 범위: 33.0~43.0 (한국)",
                },
                "longitude": {
                    "type": "number",
                    "description": "경도. 필수. 범위: 124.0~132.0 (한국)",
                },
                "waste_category": {
                    "type": "string",
                    "description": "폐기물 카테고리 (날씨 팁 맞춤용, 선택). 예: 'paper', 'plastic', 'food'",
                },
            },
            "required": ["latitude", "longitude"],
        },
    },
    {
        "name": "geocode",
        "description": (
            "장소명/주소를 좌표(위도, 경도)로 변환. "
            "사용 시점: 사용자가 '강남역 날씨', '서울 날씨' 등 "
            "특정 지역을 언급했으나 좌표가 없을 때 먼저 호출. "
            "실행 순서: 이 함수로 좌표를 먼저 얻은 후 get_weather 호출."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "place_name": {
                    "type": "string",
                    "description": (
                        "좌표로 변환할 장소명 또는 주소. "
                        "예: '강남역', '홍대입구역', '서울시 강남구', '부산 해운대'."
                    ),
                },
            },
            "required": ["place_name"],
        },
    },
]

# ============================================================
# System Prompt for Weather Agent
# ============================================================
# Best Practices Applied (2026 - GPT-5.2 CTCO Framework):
# 1. Context: 배경 정보
# 2. Task: 수행할 작업
# 3. Constraints: DO/DON'T 명시
# 4. Output: 출력 형식
# 5. Preambles: Tool 호출 전 reasoning 설명 (GPT-5.2)
# Reference: https://cookbook.openai.com/examples/gpt-5/gpt-5-1_prompting_guide

WEATHER_AGENT_SYSTEM_PROMPT = """# Context
당신은 Eco² 앱의 날씨 정보 에이전트입니다.
사용자에게 날씨 정보와 분리배출 관련 날씨 팁을 제공합니다.

# Scope Discipline
이 에이전트는 get_weather, geocode 도구만 사용합니다.
다른 작업(장소 검색, 대형폐기물 정보 등)은 도구 없이 직접 응답하세요.
절대로 정의되지 않은 도구를 호출하거나 새로운 작업을 만들어내지 마세요.

# Preambles (GPT-5.2)
도구를 호출하기 전에, 왜 그 도구를 호출하는지 간단히 설명하세요.
예: "강남역 좌표를 얻기 위해 geocode를 호출합니다."

# Tool 사용 규칙

## 사용 시점 (DO)
- 날씨 정보 요청 + 좌표 있음 → get_weather
- 날씨 정보 요청 + 지역명 언급 + 좌표 없음 → geocode 먼저 호출
- 분리배출 관련 날씨 팁 요청 → get_weather (waste_category 포함)

## 사용 금지 (DON'T)
- 분리배출 방법 질문 (날씨 무관) → 도구 사용 X, 직접 답변
- 일반 대화, 인사 → 도구 사용 X
- 이미 좌표가 있는데 geocode 호출 X
- 장소 검색, 대형폐기물 정보 → 도구 사용 X (범위 밖)

# Tool 호출 순서 (Critical)

"[지역명] 날씨" 패턴 (좌표 없음):
1. geocode(place_name="지역명") → 좌표 획득
2. get_weather(latitude=결과lat, longitude=결과lon)

"날씨 알려줘" 패턴 (user_location 있음):
1. get_weather(latitude=user_lat, longitude=user_lon)

"비오면 종이 버려도 돼?" 패턴:
1. geocode or use user_location
2. get_weather(latitude=lat, longitude=lon, waste_category="paper")

# 파라미터 규칙

- latitude/longitude: geocode 결과 또는 user_location 사용
- waste_category: 분리배출 관련이면 해당 카테고리 (paper, plastic, food 등)

# 에러 처리

- geocode 실패 → "해당 지역을 찾을 수 없습니다. 다른 지역명을 알려주세요."
- get_weather 실패 → "날씨 정보를 가져올 수 없습니다."
- 좌표 없이 get_weather 호출 시도 → 호출하지 말고 위치 요청

# 응답 형식

날씨 정보가 있으면:
1. 기온, 습도, 강수형태 요약
2. 날씨 팁 포함 (분리배출 관련이면 맞춤 팁)
3. 이모지 사용 권장 (☀️🌧️❄️)

날씨 정보가 없으면:
- 위치 정보 요청 또는 대안 제시"""


# ============================================================
# Tool Result Dataclass
# ============================================================


@dataclass
class ToolResult:
    """Tool 실행 결과."""

    tool_name: str
    success: bool
    data: dict[str, Any] | None = None
    error: str | None = None


# ============================================================
# Tool Executor
# ============================================================


class WeatherToolExecutor:
    """Weather API Tool 실행기."""

    def __init__(
        self,
        weather_client: "WeatherClientPort",
        kakao_client: "KakaoLocalClientPort | None" = None,
    ):
        self._weather_client = weather_client
        self._kakao_client = kakao_client

    async def execute(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> ToolResult:
        """Tool 실행.

        Args:
            tool_name: Tool 이름
            arguments: Tool 인자

        Returns:
            ToolResult
        """
        try:
            if tool_name == ToolName.GET_WEATHER:
                return await self._get_weather(arguments)
            elif tool_name == ToolName.GEOCODE:
                return await self._geocode(arguments)
            else:
                return ToolResult(
                    tool_name=tool_name,
                    success=False,
                    error=f"Unknown tool: {tool_name}",
                )
        except Exception as e:
            logger.exception(f"Tool execution failed: {tool_name}")
            return ToolResult(
                tool_name=tool_name,
                success=False,
                error=str(e),
            )

    async def _get_weather(self, args: dict[str, Any]) -> ToolResult:
        """날씨 조회."""
        lat = args.get("latitude")
        lon = args.get("longitude")
        waste_category = args.get("waste_category")

        if lat is None or lon is None:
            return ToolResult(
                tool_name=ToolName.GET_WEATHER,
                success=False,
                error="날씨 조회에는 좌표(latitude, longitude)가 필수입니다.",
            )

        # 위경도 → 격자좌표 변환 (WeatherService - 순수 비즈니스 로직)
        try:
            nx, ny = WeatherService.convert_to_grid(lat, lon)
        except Exception as e:
            return ToolResult(
                tool_name=ToolName.GET_WEATHER,
                success=False,
                error=f"좌표 변환 실패: {e}",
            )

        # 날씨 API 호출
        response = await self._weather_client.get_current_weather(nx, ny)

        if not response.success:
            return ToolResult(
                tool_name=ToolName.GET_WEATHER,
                success=False,
                error=response.error_message or "날씨 조회 실패",
            )

        # 날씨 팁 생성 (WeatherService - 순수 비즈니스 로직)
        tip = WeatherService.generate_weather_tip(response.current, waste_category)
        emoji = WeatherService.get_weather_emoji(response.current)

        return ToolResult(
            tool_name=ToolName.GET_WEATHER,
            success=True,
            data={
                "temperature": response.current.temperature if response.current else None,
                "humidity": response.current.humidity if response.current else None,
                "precipitation_type": (
                    response.current.precipitation_type.name if response.current else None
                ),
                "precipitation": response.current.precipitation if response.current else 0,
                "sky_status": response.current.sky_status.name if response.current else None,
                "tip": tip,
                "emoji": emoji,
                "grid": {"nx": nx, "ny": ny},
            },
        )

    async def _geocode(self, args: dict[str, Any]) -> ToolResult:
        """장소명 → 좌표 변환 (Geocoding)."""
        if self._kakao_client is None:
            return ToolResult(
                tool_name=ToolName.GEOCODE,
                success=False,
                error="Geocoding 서비스를 사용할 수 없습니다.",
            )

        place_name = args.get("place_name", "")

        # Kakao Local API로 geocoding
        response = await self._kakao_client.search_keyword(
            query=place_name,
            size=1,
        )

        if not response.places:
            return ToolResult(
                tool_name=ToolName.GEOCODE,
                success=False,
                error=f"'{place_name}'에 대한 좌표를 찾을 수 없습니다.",
            )

        place = response.places[0]
        return ToolResult(
            tool_name=ToolName.GEOCODE,
            success=True,
            data={
                "place_name": place.place_name,
                "address": place.road_address_name or place.address_name,
                "latitude": place.latitude,
                "longitude": place.longitude,
            },
        )


# ============================================================
# OpenAI Function Calling Handler
# ============================================================


async def run_openai_agent(
    openai_client: Any,  # openai.AsyncOpenAI
    model: str,
    message: str,
    user_location: dict[str, float] | None,
    tool_executor: WeatherToolExecutor,
    max_iterations: int = 5,
) -> dict[str, Any]:
    """OpenAI Function Calling으로 Weather Agent 실행.

    Args:
        openai_client: OpenAI AsyncClient
        model: 모델명 (gpt-5.2, etc.)
        message: 사용자 메시지
        user_location: 사용자 위치 {latitude, longitude}
        tool_executor: Weather Tool 실행기
        max_iterations: 최대 반복 횟수

    Returns:
        Agent 결과 (weather_data, summary 등)
    """
    # 사용자 위치 정보를 메시지에 포함
    user_message = message
    if user_location:
        lat = user_location.get("latitude") or user_location.get("lat")
        lon = user_location.get("longitude") or user_location.get("lon")
        if lat and lon:
            user_message = f"{message}\n\n[현재 위치: 위도 {lat}, 경도 {lon}]"

    messages = [
        {"role": "system", "content": WEATHER_AGENT_SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]

    all_tool_results: list[dict[str, Any]] = []

    for iteration in range(max_iterations):
        logger.debug(f"OpenAI weather agent iteration {iteration + 1}")

        response = await openai_client.chat.completions.create(
            model=model,
            messages=messages,
            tools=OPENAI_TOOLS,
            tool_choice="auto",
        )

        assistant_message = response.choices[0].message

        # Tool call이 없으면 최종 응답
        if not assistant_message.tool_calls:
            return {
                "success": True,
                "summary": assistant_message.content,
                "tool_results": all_tool_results,
            }

        # Tool calls 처리
        messages.append(assistant_message.model_dump())

        # 병렬 Tool 실행 (asyncio.gather) - GPT-5.2 Best Practice
        async def execute_tool(tc: Any) -> tuple[Any, dict, ToolResult]:
            tool_name = tc.function.name
            try:
                arguments = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                arguments = {}

            logger.info(
                "Executing weather tool",
                extra={"tool": tool_name, "args": arguments},
            )
            result = await tool_executor.execute(tool_name, arguments)
            return tc, arguments, result

        # 모든 tool calls 병렬 실행
        execution_results = await asyncio.gather(
            *[execute_tool(tc) for tc in assistant_message.tool_calls]
        )

        # 결과 처리 및 메시지 추가
        for tc, arguments, result in execution_results:
            all_tool_results.append({
                "tool": tc.function.name,
                "arguments": arguments,
                "result": result.data if result.success else {"error": result.error},
                "success": result.success,
            })

            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "name": tc.function.name,
                "content": json.dumps(
                    result.data if result.success else {"error": result.error},
                    ensure_ascii=False,
                ),
            })

    # Max iterations 도달
    return {
        "success": True,
        "summary": "날씨 정보를 처리했습니다.",
        "tool_results": all_tool_results,
    }


# ============================================================
# Gemini Function Calling Handler
# ============================================================


async def run_gemini_agent(
    gemini_client: Any,  # google.genai.Client
    model: str,
    message: str,
    user_location: dict[str, float] | None,
    tool_executor: WeatherToolExecutor,
    max_iterations: int = 5,
) -> dict[str, Any]:
    """Gemini Function Calling으로 Weather Agent 실행.

    Args:
        gemini_client: Gemini Client
        model: 모델명 (gemini-3-flash, etc.)
        message: 사용자 메시지
        user_location: 사용자 위치 {latitude, longitude}
        tool_executor: Weather Tool 실행기
        max_iterations: 최대 반복 횟수

    Returns:
        Agent 결과 (weather_data, summary 등)
    """
    from google.genai import types

    # 사용자 위치 정보를 메시지에 포함
    user_message = message
    if user_location:
        lat = user_location.get("latitude") or user_location.get("lat")
        lon = user_location.get("longitude") or user_location.get("lon")
        if lat and lon:
            user_message = f"{message}\n\n[현재 위치: 위도 {lat}, 경도 {lon}]"

    # Gemini 3 Tool 설정
    tools = types.Tool(function_declarations=GEMINI_TOOLS)
    config = types.GenerateContentConfig(
        tools=[tools],
        tool_config=types.ToolConfig(
            function_calling_config=types.FunctionCallingConfig(
                mode="AUTO",
            ),
        ),
        system_instruction=WEATHER_AGENT_SYSTEM_PROMPT,
        temperature=0,
    )

    contents = [user_message]
    all_tool_results: list[dict[str, Any]] = []

    for iteration in range(max_iterations):
        logger.debug(f"Gemini weather agent iteration {iteration + 1}")

        response = await gemini_client.aio.models.generate_content(
            model=model,
            contents=contents,
            config=config,
        )

        candidate = response.candidates[0]
        parts = candidate.content.parts

        # Parallel Function Calls 처리
        function_calls = [
            p for p in parts
            if hasattr(p, "function_call") and p.function_call is not None
        ]

        if not function_calls:
            # 최종 텍스트 응답
            text_parts = [p.text for p in parts if hasattr(p, "text") and p.text]
            return {
                "success": True,
                "summary": " ".join(text_parts) if text_parts else "",
                "tool_results": all_tool_results,
            }

        # 병렬 Tool 실행
        async def execute_tool(fc_part: Any) -> dict[str, Any]:
            fc = fc_part.function_call
            tool_name = fc.name
            arguments = dict(fc.args) if fc.args else {}
            logger.info(
                "Executing weather tool (Gemini)",
                extra={"tool": tool_name, "args": arguments},
            )
            result = await tool_executor.execute(tool_name, arguments)
            return {
                "tool": tool_name,
                "arguments": arguments,
                "result": result.data if result.success else {"error": result.error},
                "success": result.success,
                "_name": tool_name,
                "_response": result.data if result.success else {"error": result.error},
            }

        results = await asyncio.gather(*[execute_tool(fc) for fc in function_calls])
        all_tool_results.extend(results)

        # 대화 이력에 추가
        contents.append(candidate.content)

        # 모든 Function 결과를 하나의 Content로 추가
        function_response_parts = [
            types.Part.from_function_response(
                name=r["_name"],
                response=r["_response"],
            )
            for r in results
        ]
        contents.append(types.Content(role="user", parts=function_response_parts))

    # Max iterations 도달
    return {
        "success": True,
        "summary": "날씨 정보를 처리했습니다.",
        "tool_results": all_tool_results,
    }


# ============================================================
# Weather Agent Node Factory
# ============================================================


def create_weather_agent_node(
    weather_client: "WeatherClientPort",
    event_publisher: "ProgressNotifierPort",
    kakao_client: "KakaoLocalClientPort | None" = None,
    openai_client: Any | None = None,
    gemini_client: Any | None = None,
    default_model: str = "gpt-5.2",
    default_provider: str = "openai",
):
    """Weather Agent 노드 팩토리.

    LLM이 Weather/Geocoding API를 Tool로 사용하여 날씨 정보 제공.
    GPT-5.2 / Gemini 3 지원.

    Args:
        weather_client: 날씨 클라이언트
        event_publisher: 이벤트 발행기
        kakao_client: Kakao Local API 클라이언트 (geocoding용)
        openai_client: OpenAI AsyncClient (선택)
        gemini_client: Gemini Client (선택)
        default_model: 기본 모델명 (gpt-5.2, gemini-3-flash 등)
        default_provider: 기본 프로바이더 ("openai" | "gemini")

    Returns:
        weather_agent_node 함수
    """
    tool_executor = WeatherToolExecutor(
        weather_client=weather_client,
        kakao_client=kakao_client,
    )

    async def weather_agent_node(state: dict[str, Any]) -> dict[str, Any]:
        """LangGraph Weather Agent 노드.

        Args:
            state: 현재 LangGraph 상태

        Returns:
            업데이트된 상태 (weather_context)
        """
        job_id = state.get("job_id", "")
        message = state.get("message", "")
        user_location = state.get("user_location")

        # Progress: 시작
        await event_publisher.notify_stage(
            task_id=job_id,
            stage="weather",
            status="started",
            progress=40,
            message="날씨 정보 확인 중...",
        )

        try:
            # Provider 선택 (state에서 override 가능)
            provider = state.get("llm_provider", default_provider)
            model = state.get("llm_model", default_model)

            if provider == "gemini" and gemini_client is not None:
                result = await run_gemini_agent(
                    gemini_client=gemini_client,
                    model=model,
                    message=message,
                    user_location=user_location,
                    tool_executor=tool_executor,
                )
            elif openai_client is not None:
                result = await run_openai_agent(
                    openai_client=openai_client,
                    model=model,
                    message=message,
                    user_location=user_location,
                    tool_executor=tool_executor,
                )
            else:
                # Fallback: LLM 없으면 직접 날씨 조회
                logger.warning("No LLM client available, falling back to direct weather fetch")

                # user_location에서 좌표 추출
                lat = None
                lon = None
                if isinstance(user_location, dict):
                    lat = user_location.get("latitude") or user_location.get("lat")
                    lon = user_location.get("longitude") or user_location.get("lon")

                if lat and lon:
                    weather_result = await tool_executor._get_weather({
                        "latitude": lat,
                        "longitude": lon,
                    })
                    result = {
                        "success": weather_result.success,
                        "summary": None,
                        "tool_results": [{
                            "tool": "get_weather",
                            "result": weather_result.data if weather_result.success else {"error": weather_result.error},
                            "success": weather_result.success,
                        }],
                    }
                else:
                    result = {
                        "success": False,
                        "summary": None,
                        "tool_results": [],
                        "error": "위치 정보가 없습니다.",
                    }

            # 결과에서 날씨 정보 추출
            weather_data = None
            for tr in result.get("tool_results", []):
                if tr.get("tool") == "get_weather" and tr.get("success"):
                    weather_data = tr.get("result")
                    break

            # Progress: 완료
            if weather_data:
                temp = weather_data.get("temperature")
                await event_publisher.notify_stage(
                    task_id=job_id,
                    stage="weather",
                    status="completed",
                    progress=45,
                    result={
                        "temperature": temp,
                        "has_tip": bool(weather_data.get("tip")),
                    },
                    message=f"날씨 확인 완료: {temp}°C" if temp else "날씨 확인 완료",
                )

                # weather_context 생성
                context_data = {
                    "type": "weather",
                    "temperature": weather_data.get("temperature"),
                    "humidity": weather_data.get("humidity"),
                    "precipitation_type": weather_data.get("precipitation_type"),
                    "tip": weather_data.get("tip"),
                    "emoji": weather_data.get("emoji"),
                    "summary": result.get("summary"),
                    "context": result.get("summary"),  # Answer 노드에서 사용
                }

                return {
                    "weather_context": create_context(
                        data=context_data,
                        producer="weather",
                        job_id=job_id,
                    ),
                }
            else:
                # 날씨 정보 없음
                await event_publisher.notify_stage(
                    task_id=job_id,
                    stage="weather",
                    status="skipped",
                    message="날씨 정보 없음",
                )

                return {
                    "weather_context": create_error_context(
                        producer="weather",
                        job_id=job_id,
                        error=result.get("error", "날씨 정보를 가져올 수 없습니다."),
                    ),
                }

        except Exception as e:
            logger.exception("Weather agent failed")

            await event_publisher.notify_stage(
                task_id=job_id,
                stage="weather",
                status="failed",
                result={"error": str(e)},
            )

            return {
                "weather_context": create_error_context(
                    producer="weather",
                    job_id=job_id,
                    error=str(e),
                ),
            }

    return weather_agent_node


__all__ = [
    "create_weather_agent_node",
    "OPENAI_TOOLS",
    "GEMINI_TOOLS",
    "WeatherToolExecutor",
]
