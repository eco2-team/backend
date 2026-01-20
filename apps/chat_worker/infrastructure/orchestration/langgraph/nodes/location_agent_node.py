"""Location Agent Node - LLM with Kakao API Tools.

LLM이 Kakao Map API를 Tool로 사용하여 장소 검색을 수행하는 에이전트 노드.

Architecture:
- LLM이 사용자 메시지를 분석하여 적절한 Tool 선택
- Tool 실행 결과를 LLM이 해석하여 자연어 context 생성
- OpenAI/Gemini 모두 지원 (Function Calling)

Tools:
- search_places: 키워드로 장소 검색 (재활용센터, 제로웨이스트샵 등)
- search_category: 카테고리로 주변 장소 검색 (카페, 음식점 등)
- geocode: 장소명을 좌표로 변환

Flow:
    Router → location_agent → Answer
             └─ LLM analyzes message
             └─ LLM calls tools (Kakao API)
             └─ LLM interprets results
             └─ Returns location_context
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any

from chat_worker.application.ports.kakao_local_client import (
    KakaoCategoryGroup,
    KakaoSearchResponse,
)
from chat_worker.infrastructure.orchestration.langgraph.context_helper import (
    create_context,
    create_error_context,
)

if TYPE_CHECKING:
    from chat_worker.application.ports.events import ProgressNotifierPort
    from chat_worker.application.ports.kakao_local_client import KakaoLocalClientPort

logger = logging.getLogger(__name__)


# ============================================================
# Tool Definitions
# ============================================================


class ToolName(str, Enum):
    """사용 가능한 Tool 이름."""

    SEARCH_PLACES = "search_places"
    SEARCH_CATEGORY = "search_category"
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
            "name": "search_places",
            "description": (
                "키워드 기반 장소 검색. "
                "사용 시점: 사용자가 '재활용센터', '제로웨이스트샵', '분리수거장' 등 "
                "특정 장소 유형을 키워드로 찾을 때 호출. "
                "좌표가 없으면 전국 검색, 좌표가 있으면 해당 위치 주변 검색. "
                "주의: 사용자가 '강남역 근처 재활용센터'라고 하면 먼저 geocode로 "
                "'강남역' 좌표를 얻은 후 이 함수 호출."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": (
                            "검색 키워드. 장소 유형을 포함해야 함. "
                            "예: '재활용센터', '제로웨이스트샵', '폐건전지 수거함'. "
                            "지역명은 포함하지 않음 (좌표로 처리)."
                        ),
                    },
                    "latitude": {
                        "type": "number",
                        "description": "검색 중심 위도. 주변 검색 시 필수. 범위: 33.0~43.0 (한국)",
                    },
                    "longitude": {
                        "type": "number",
                        "description": "검색 중심 경도. 주변 검색 시 필수. 범위: 124.0~132.0 (한국)",
                    },
                    "radius": {
                        "type": "integer",
                        "description": "검색 반경(미터). 기본 5000m. 최대 20000m.",
                    },
                },
                "required": ["query"],
                "additionalProperties": False,
            },
            "strict": True,
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_category",
            "description": (
                "카테고리 기반 주변 장소 검색. 좌표 필수. "
                "사용 시점: 사용자가 '주변 카페', '근처 편의점', '가까운 약국' 등 "
                "일반적인 장소 카테고리를 찾을 때 호출. "
                "주의: 좌표 없이 호출 불가. 사용자 위치가 없고 지역명만 있으면 "
                "먼저 geocode로 좌표를 얻은 후 호출. "
                "재활용센터, 제로웨이스트샵 등 특수 장소는 search_places 사용."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "enum": [
                            "MART",
                            "CONVENIENCE",
                            "SUBWAY",
                            "CAFE",
                            "RESTAURANT",
                            "HOSPITAL",
                            "PHARMACY",
                            "BANK",
                            "GAS_STATION",
                            "PARKING",
                        ],
                        "description": (
                            "장소 카테고리. "
                            "MART=대형마트, CONVENIENCE=편의점, SUBWAY=지하철역, "
                            "CAFE=카페, RESTAURANT=음식점, HOSPITAL=병원, "
                            "PHARMACY=약국, BANK=은행, GAS_STATION=주유소, PARKING=주차장"
                        ),
                    },
                    "latitude": {
                        "type": "number",
                        "description": "검색 중심 위도. 필수. 범위: 33.0~43.0 (한국)",
                    },
                    "longitude": {
                        "type": "number",
                        "description": "검색 중심 경도. 필수. 범위: 124.0~132.0 (한국)",
                    },
                    "radius": {
                        "type": "integer",
                        "description": "검색 반경(미터). 기본 5000m. 최대 20000m.",
                    },
                },
                "required": ["category", "latitude", "longitude"],
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
                "사용 시점: 사용자가 '강남역', '홍대입구', '서울시청' 등 "
                "특정 지역을 언급했으나 좌표가 없을 때 먼저 호출. "
                "실행 순서: 이 함수로 좌표를 먼저 얻은 후 search_places 또는 "
                "search_category 호출. "
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
# 2. Strong-typed parameters with enums
# 3. Parallel & Compositional function calling 지원
# Reference: https://ai.google.dev/gemini-api/docs/function-calling

GEMINI_TOOLS = [
    {
        "name": "search_places",
        "description": (
            "키워드 기반 장소 검색. "
            "사용 시점: 사용자가 '재활용센터', '제로웨이스트샵', '분리수거장' 등 "
            "특정 장소 유형을 키워드로 찾을 때 호출. "
            "좌표가 없으면 전국 검색, 좌표가 있으면 해당 위치 주변 검색. "
            "주의: 사용자가 '강남역 근처 재활용센터'라고 하면 먼저 geocode로 "
            "'강남역' 좌표를 얻은 후 이 함수 호출."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "검색 키워드. 장소 유형을 포함해야 함. "
                        "예: '재활용센터', '제로웨이스트샵', '폐건전지 수거함'. "
                        "지역명은 포함하지 않음 (좌표로 처리)."
                    ),
                },
                "latitude": {
                    "type": "number",
                    "description": "검색 중심 위도. 주변 검색 시 필수. 범위: 33.0~43.0 (한국)",
                },
                "longitude": {
                    "type": "number",
                    "description": "검색 중심 경도. 주변 검색 시 필수. 범위: 124.0~132.0 (한국)",
                },
                "radius": {
                    "type": "integer",
                    "description": "검색 반경(미터). 기본 5000m. 최대 20000m.",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "search_category",
        "description": (
            "카테고리 기반 주변 장소 검색. 좌표 필수. "
            "사용 시점: 사용자가 '주변 카페', '근처 편의점', '가까운 약국' 등 "
            "일반적인 장소 카테고리를 찾을 때 호출. "
            "주의: 좌표 없이 호출 불가. 사용자 위치가 없고 지역명만 있으면 "
            "먼저 geocode로 좌표를 얻은 후 호출. "
            "재활용센터, 제로웨이스트샵 등 특수 장소는 search_places 사용."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "enum": [
                        "MART",
                        "CONVENIENCE",
                        "SUBWAY",
                        "CAFE",
                        "RESTAURANT",
                        "HOSPITAL",
                        "PHARMACY",
                        "BANK",
                        "GAS_STATION",
                        "PARKING",
                    ],
                    "description": (
                        "장소 카테고리. "
                        "MART=대형마트, CONVENIENCE=편의점, SUBWAY=지하철역, "
                        "CAFE=카페, RESTAURANT=음식점, HOSPITAL=병원, "
                        "PHARMACY=약국, BANK=은행, GAS_STATION=주유소, PARKING=주차장"
                    ),
                },
                "latitude": {
                    "type": "number",
                    "description": "검색 중심 위도. 필수. 범위: 33.0~43.0 (한국)",
                },
                "longitude": {
                    "type": "number",
                    "description": "검색 중심 경도. 필수. 범위: 124.0~132.0 (한국)",
                },
                "radius": {
                    "type": "integer",
                    "description": "검색 반경(미터). 기본 5000m. 최대 20000m.",
                },
            },
            "required": ["category", "latitude", "longitude"],
        },
    },
    {
        "name": "geocode",
        "description": (
            "장소명/주소를 좌표(위도, 경도)로 변환. "
            "사용 시점: 사용자가 '강남역', '홍대입구', '서울시청' 등 "
            "특정 지역을 언급했으나 좌표가 없을 때 먼저 호출. "
            "실행 순서: 이 함수로 좌표를 먼저 얻은 후 search_places 또는 "
            "search_category 호출. "
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
        },
    },
]

# ============================================================
# System Prompt for Location Agent
# ============================================================
# Best Practices Applied (2026 - GPT-5.2 CTCO Framework):
# 1. Context: 배경 정보
# 2. Task: 수행할 작업
# 3. Constraints: DO/DON'T 명시
# 4. Output: 출력 형식
# 5. Preambles: Tool 호출 전 reasoning 설명 (GPT-5.2)
# Reference: https://cookbook.openai.com/examples/gpt-5/gpt-5-1_prompting_guide

LOCATION_AGENT_SYSTEM_PROMPT = """# Context
당신은 Eco² 앱의 위치 기반 장소 검색 에이전트입니다.
사용자가 재활용센터, 제로웨이스트샵, 주변 시설을 찾을 때 도구를 사용해 정보를 제공합니다.

# Scope Discipline
이 에이전트는 search_places, search_category, geocode 도구만 사용합니다.
다른 작업(분리배출 방법 안내, 일반 대화, 날씨 정보 등)은 도구 없이 직접 응답하세요.
절대로 정의되지 않은 도구를 호출하거나 새로운 작업을 만들어내지 마세요.

# Preambles (GPT-5.2)
도구를 호출하기 전에, 왜 그 도구를 호출하는지 간단히 설명하세요.
예: "강남역 좌표를 얻기 위해 geocode를 호출합니다."

# Tool 사용 규칙

## 사용 시점 (DO)
- 재활용센터, 제로웨이스트샵, 분리수거장 검색 → search_places
- 주변 카페, 편의점, 약국 등 일반 시설 검색 → search_category
- 지역명(강남역, 홍대 등) 언급 + 좌표 없음 → geocode 먼저 호출

## 사용 금지 (DON'T)
- 분리배출 방법 질문 → 도구 사용 X, 직접 답변
- 일반 대화, 인사 → 도구 사용 X
- 이미 좌표가 있는데 geocode 호출 X

# Tool 호출 순서 (Critical)

"[지역명] 근처 [장소]" 패턴:
1. geocode(place_name="지역명") → 좌표 획득
2. search_places(query="장소", latitude=결과lat, longitude=결과lon)

"주변 [카테고리]" 패턴 (user_location 있음):
1. search_category(category="카테고리", latitude=user_lat, longitude=user_lon)

"주변 [카테고리]" 패턴 (user_location 없음):
→ "위치 정보가 필요합니다" 안내 (도구 호출 X)

# 파라미터 규칙

- query: 장소 유형만 포함 (지역명 제외). "재활용센터" O, "강남역 재활용센터" X
- latitude/longitude: geocode 결과 또는 user_location 사용
- radius: 기본 5000m, 넓은 범위 요청 시 최대 20000m

# 에러 처리

- geocode 실패 → "해당 지역을 찾을 수 없습니다. 다른 지역명을 알려주세요."
- 검색 결과 없음 → "해당 지역에서 [장소]를 찾을 수 없습니다."
- 좌표 없이 search_category 호출 시도 → 호출하지 말고 위치 요청

# 응답 형식

검색 결과가 있으면:
1. 가장 가까운 장소 1-3개 요약
2. 장소명, 주소, 거리 포함
3. 전화번호가 있으면 포함

검색 결과가 없으면:
- 대안 제시 (다른 검색어, 반경 확대 등)"""


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


class KakaoToolExecutor:
    """Kakao API Tool 실행기."""

    def __init__(self, kakao_client: "KakaoLocalClientPort"):
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
            if tool_name == ToolName.SEARCH_PLACES:
                return await self._search_places(arguments)
            elif tool_name == ToolName.SEARCH_CATEGORY:
                return await self._search_category(arguments)
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

    async def _search_places(self, args: dict[str, Any]) -> ToolResult:
        """키워드 장소 검색."""
        query = args.get("query", "")
        lat = args.get("latitude")
        lon = args.get("longitude")
        radius = args.get("radius", 5000)

        response = await self._kakao_client.search_keyword(
            query=query,
            x=lon,  # Kakao API는 x=경도, y=위도
            y=lat,
            radius=radius,
            size=10,
            sort="distance" if lat and lon else "accuracy",
        )

        return ToolResult(
            tool_name=ToolName.SEARCH_PLACES,
            success=True,
            data=self._format_search_response(response),
        )

    async def _search_category(self, args: dict[str, Any]) -> ToolResult:
        """카테고리 장소 검색."""
        category = args.get("category", "")
        lat = args.get("latitude")
        lon = args.get("longitude")
        radius = args.get("radius", 5000)

        if lat is None or lon is None:
            return ToolResult(
                tool_name=ToolName.SEARCH_CATEGORY,
                success=False,
                error="카테고리 검색에는 좌표(latitude, longitude)가 필수입니다.",
            )

        # Category enum 매핑
        category_code = getattr(KakaoCategoryGroup, category, None)
        if category_code is None:
            return ToolResult(
                tool_name=ToolName.SEARCH_CATEGORY,
                success=False,
                error=f"알 수 없는 카테고리: {category}",
            )

        response = await self._kakao_client.search_category(
            category_group_code=category_code.value,
            x=lon,
            y=lat,
            radius=radius,
            size=10,
            sort="distance",
        )

        return ToolResult(
            tool_name=ToolName.SEARCH_CATEGORY,
            success=True,
            data=self._format_search_response(response),
        )

    async def _geocode(self, args: dict[str, Any]) -> ToolResult:
        """장소명 → 좌표 변환 (Geocoding)."""
        place_name = args.get("place_name", "")

        # search_keyword로 geocoding (첫 번째 결과 사용)
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

    def _format_search_response(self, response: KakaoSearchResponse) -> dict[str, Any]:
        """검색 응답을 LLM이 이해하기 쉬운 형태로 변환."""
        places = []
        for p in response.places[:10]:  # 최대 10개
            places.append({
                "name": p.place_name,
                "address": p.road_address_name or p.address_name,
                "phone": p.phone,
                "distance": p.distance_text,
                "category": p.category_name,
                "url": p.place_url,
                "latitude": p.latitude,
                "longitude": p.longitude,
            })

        return {
            "query": response.query,
            "total_count": response.meta.total_count if response.meta else 0,
            "places": places,
            "found": len(places) > 0,
        }


# ============================================================
# OpenAI Function Calling Handler
# ============================================================


async def run_openai_agent(
    openai_client: Any,  # openai.AsyncOpenAI
    model: str,
    message: str,
    user_location: dict[str, float] | None,
    tool_executor: KakaoToolExecutor,
    max_iterations: int = 5,
) -> dict[str, Any]:
    """OpenAI Function Calling으로 Location Agent 실행.

    Args:
        openai_client: OpenAI AsyncClient
        model: 모델명
        message: 사용자 메시지
        user_location: 사용자 위치 {latitude, longitude}
        tool_executor: Kakao Tool 실행기
        max_iterations: 최대 반복 횟수

    Returns:
        Agent 결과 (places, summary 등)
    """
    # 사용자 위치 정보를 메시지에 포함
    user_message = message
    if user_location:
        lat = user_location.get("latitude") or user_location.get("lat")
        lon = user_location.get("longitude") or user_location.get("lon")
        if lat and lon:
            user_message = f"{message}\n\n[현재 위치: 위도 {lat}, 경도 {lon}]"

    messages = [
        {"role": "system", "content": LOCATION_AGENT_SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]

    all_tool_results: list[dict[str, Any]] = []

    for iteration in range(max_iterations):
        logger.debug(f"OpenAI agent iteration {iteration + 1}")

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
        async def execute_tool(tc: Any) -> tuple[Any, ToolResult]:
            tool_name = tc.function.name
            try:
                arguments = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                arguments = {}

            logger.info(
                "Executing tool",
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
        "summary": "검색 결과를 처리했습니다.",
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
    tool_executor: KakaoToolExecutor,
    max_iterations: int = 5,
) -> dict[str, Any]:
    """Gemini Function Calling으로 Location Agent 실행.

    Args:
        gemini_client: Gemini Client
        model: 모델명
        message: 사용자 메시지
        user_location: 사용자 위치 {latitude, longitude}
        tool_executor: Kakao Tool 실행기
        max_iterations: 최대 반복 횟수

    Returns:
        Agent 결과 (places, summary 등)
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
    # Best Practices (2026):
    # - temperature=0 for deterministic tool selection
    # - VALIDATED mode for schema adherence (optional)
    tools = types.Tool(function_declarations=GEMINI_TOOLS)
    config = types.GenerateContentConfig(
        tools=[tools],
        tool_config=types.ToolConfig(
            function_calling_config=types.FunctionCallingConfig(
                mode="AUTO",  # AUTO | ANY | NONE | VALIDATED
            ),
        ),
        system_instruction=LOCATION_AGENT_SYSTEM_PROMPT,
        temperature=0,  # Gemini 3: 결정론적 Tool 선택
    )

    contents = [user_message]
    all_tool_results: list[dict[str, Any]] = []

    for iteration in range(max_iterations):
        logger.debug(f"Gemini agent iteration {iteration + 1}")

        response = await gemini_client.aio.models.generate_content(
            model=model,
            contents=contents,
            config=config,
        )

        candidate = response.candidates[0]
        parts = candidate.content.parts

        # Parallel Function Calls 처리 (Gemini 3 지원)
        # 여러 function call이 동시에 반환될 수 있음
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

        # 병렬 Tool 실행 (asyncio.gather)
        async def execute_tool(fc_part: Any) -> dict[str, Any]:
            fc = fc_part.function_call
            tool_name = fc.name
            arguments = dict(fc.args) if fc.args else {}
            logger.info(
                "Executing tool (Gemini)",
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
        "summary": "검색 결과를 처리했습니다.",
        "tool_results": all_tool_results,
    }


# ============================================================
# Location Agent Node Factory
# ============================================================


def create_location_agent_node(
    kakao_client: "KakaoLocalClientPort",
    event_publisher: "ProgressNotifierPort",
    openai_client: Any | None = None,
    gemini_client: Any | None = None,
    default_model: str = "gpt-5.2",  # GPT-5.2 (2026)
    default_provider: str = "openai",
):
    """Location Agent 노드 팩토리.

    LLM이 Kakao API를 Tool로 사용하여 장소 검색을 수행.
    GPT-5.2 / Gemini 3 지원.

    Args:
        kakao_client: Kakao Local API 클라이언트
        event_publisher: 이벤트 발행기
        openai_client: OpenAI AsyncClient (선택)
        gemini_client: Gemini Client (선택)
        default_model: 기본 모델명 (gpt-5.2, gemini-3-flash 등)
        default_provider: 기본 프로바이더 ("openai" | "gemini")

    Returns:
        location_agent_node 함수
    """
    tool_executor = KakaoToolExecutor(kakao_client)

    async def location_agent_node(state: dict[str, Any]) -> dict[str, Any]:
        """LangGraph Location Agent 노드.

        Args:
            state: 현재 LangGraph 상태

        Returns:
            업데이트된 상태 (location_context)
        """
        job_id = state.get("job_id", "")
        message = state.get("message", "")
        user_location = state.get("user_location")

        # Progress: 시작
        await event_publisher.notify_stage(
            task_id=job_id,
            stage="location",
            status="started",
            progress=45,
            message="장소 검색 중...",
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
                # Fallback: 직접 키워드 검색
                logger.warning("No LLM client available, falling back to direct search")
                response = await kakao_client.search_keyword(query=message, size=10)
                result = {
                    "success": True,
                    "summary": None,
                    "tool_results": [{
                        "tool": "search_places",
                        "result": tool_executor._format_search_response(response),
                        "success": True,
                    }],
                }

            # 결과에서 장소 정보 추출
            places = []
            for tr in result.get("tool_results", []):
                if tr.get("success") and tr.get("result", {}).get("places"):
                    places.extend(tr["result"]["places"])

            # Progress: 완료
            found = len(places) > 0
            await event_publisher.notify_stage(
                task_id=job_id,
                stage="location",
                status="completed",
                progress=55,
                result={
                    "found": found,
                    "count": len(places),
                },
                message=f"{len(places)}개 장소 검색 완료" if found else "검색 결과 없음",
            )

            # location_context 생성
            context_data = {
                "found": found,
                "places": places[:10],  # 최대 10개
                "summary": result.get("summary"),
                "tool_calls": [
                    {"tool": tr["tool"], "success": tr["success"]}
                    for tr in result.get("tool_results", [])
                ],
            }

            return {
                "location_context": create_context(
                    data=context_data,
                    producer="location",
                    job_id=job_id,
                ),
            }

        except Exception as e:
            logger.exception("Location agent failed")

            await event_publisher.notify_stage(
                task_id=job_id,
                stage="location",
                status="failed",
                result={"error": str(e)},
            )

            return {
                "location_context": create_error_context(
                    producer="location",
                    job_id=job_id,
                    error=str(e),
                ),
            }

    return location_agent_node


__all__ = [
    "create_location_agent_node",
    "OPENAI_TOOLS",
    "GEMINI_TOOLS",
    "KakaoToolExecutor",
]
