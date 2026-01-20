"""Collection Point Agent Node - LLM with Collection Point API Tools.

LLM이 수거함 위치 API를 Tool로 사용하여 폐전자제품/폐건전지 수거함 정보를 제공하는 에이전트 노드.

Architecture:
- LLM이 사용자 메시지를 분석하여 지역/상호명 추출
- Tool 실행 결과를 LLM이 해석하여 자연어 응답 생성
- OpenAI/Gemini 모두 지원 (Function Calling)

Tools:
- search_collection_points: 주소/상호명으로 수거함 검색
- get_nearby_collection_points: 좌표 기반 주변 수거함 검색

Flow:
    Router → collection_point_agent → Answer
             └─ LLM analyzes message (extracts 지역, 품목)
             └─ LLM calls tools (Collection Point API)
             └─ LLM generates location summary
             └─ Returns collection_point_context
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any

from chat_worker.infrastructure.orchestration.langgraph.context_helper import (
    create_context,
    create_error_context,
)

if TYPE_CHECKING:
    from chat_worker.application.ports.collection_point_client import (
        CollectionPointClientPort,
    )
    from chat_worker.application.ports.events import ProgressNotifierPort
    from chat_worker.application.ports.kakao_local_client import KakaoLocalClientPort

logger = logging.getLogger(__name__)


# ============================================================
# Tool Definitions
# ============================================================


class ToolName(str, Enum):
    """사용 가능한 Tool 이름."""

    SEARCH_COLLECTION_POINTS = "search_collection_points"
    GET_NEARBY_COLLECTION_POINTS = "get_nearby_collection_points"
    GEOCODE = "geocode"


# ============================================================
# OpenAI Function Calling Tools (GPT-5.2 Strict Mode)
# ============================================================

OPENAI_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_collection_points",
            "description": (
                "주소 또는 상호명으로 폐전자제품/폐건전지 수거함 검색. "
                "사용 시점: 사용자가 '강남구 폐전자제품 수거함', '이마트 수거함' 등 "
                "특정 지역이나 장소의 수거함을 찾을 때 호출. "
                "반환값: 수거함 위치, 상호명, 수거 품목, 주소. "
                "주의: address_keyword 또는 name_keyword 중 하나 이상 필요."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "address_keyword": {
                        "type": "string",
                        "description": (
                            "주소 검색어. 구/동 단위 권장. "
                            "예: '강남구', '용산', '해운대구', '서초동'."
                        ),
                    },
                    "name_keyword": {
                        "type": "string",
                        "description": (
                            "상호명 검색어. "
                            "예: '이마트', '홈플러스', '주민센터', '구청'."
                        ),
                    },
                },
                "required": [],
                "additionalProperties": False,
            },
            "strict": True,
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_nearby_collection_points",
            "description": (
                "좌표 기반 주변 수거함 검색. "
                "사용 시점: 사용자가 '주변 수거함', '가까운 폐건전지 수거함' 등 "
                "현재 위치 기반으로 수거함을 찾을 때 호출. "
                "반환값: 거리순 정렬된 수거함 목록. "
                "주의: latitude, longitude 필수. user_location이 있으면 그 값 사용. "
                "user_location이 없고 지역명만 있으면 먼저 geocode 호출."
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
                    "radius_km": {
                        "type": "number",
                        "description": "검색 반경(km). 기본 2.0, 최대 5.0.",
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
                "사용 시점: 사용자가 '강남역 주변 수거함' 등 특정 지역을 언급했으나 "
                "좌표가 없을 때 먼저 호출. "
                "실행 순서: 이 함수로 좌표를 먼저 얻은 후 get_nearby_collection_points 호출. "
                "주의: user_location이 이미 있으면 호출 불필요."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "place_name": {
                        "type": "string",
                        "description": (
                            "좌표로 변환할 장소명 또는 주소. "
                            "예: '강남역', '홍대입구역', '서울시 강남구'."
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

GEMINI_TOOLS = [
    {
        "name": "search_collection_points",
        "description": (
            "주소 또는 상호명으로 폐전자제품/폐건전지 수거함 검색. "
            "사용 시점: 사용자가 특정 지역이나 장소의 수거함을 찾을 때 호출. "
            "반환값: 수거함 위치, 상호명, 수거 품목, 주소."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "address_keyword": {
                    "type": "string",
                    "description": "주소 검색어. 예: '강남구', '용산', '해운대구'.",
                },
                "name_keyword": {
                    "type": "string",
                    "description": "상호명 검색어. 예: '이마트', '주민센터'.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "get_nearby_collection_points",
        "description": (
            "좌표 기반 주변 수거함 검색. "
            "사용 시점: 사용자가 현재 위치 기반으로 수거함을 찾을 때 호출. "
            "반환값: 거리순 정렬된 수거함 목록. "
            "주의: latitude, longitude 필수."
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
                "radius_km": {
                    "type": "number",
                    "description": "검색 반경(km). 기본 2.0, 최대 5.0.",
                },
            },
            "required": ["latitude", "longitude"],
        },
    },
    {
        "name": "geocode",
        "description": (
            "장소명/주소를 좌표(위도, 경도)로 변환. "
            "사용 시점: 지역명 언급 시 좌표가 필요할 때 먼저 호출. "
            "user_location이 이미 있으면 불필요."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "place_name": {
                    "type": "string",
                    "description": "좌표로 변환할 장소명 또는 주소. 예: '강남역', '서울시 강남구'.",
                },
            },
            "required": ["place_name"],
        },
    },
]

# ============================================================
# System Prompt for Collection Point Agent
# ============================================================

COLLECTION_POINT_AGENT_SYSTEM_PROMPT = """# Context
당신은 Eco² 앱의 수거함 위치 검색 에이전트입니다.
사용자에게 폐전자제품, 폐건전지, 폐형광등 수거함 위치 정보를 제공합니다.

# Scope Discipline
이 에이전트는 search_collection_points, get_nearby_collection_points, geocode 도구만 사용합니다.
다른 작업(날씨, 대형폐기물, 재활용 시세 등)은 도구 없이 직접 응답하세요.
절대로 정의되지 않은 도구를 호출하거나 새로운 작업을 만들어내지 마세요.

# Preambles (GPT-5.2)
도구를 호출하기 전에, 왜 그 도구를 호출하는지 간단히 설명하세요.
예: "강남구의 수거함을 검색하기 위해 search_collection_points를 호출합니다."

# Tool 사용 규칙

## 사용 시점 (DO)
- 특정 지역 수거함 검색 → search_collection_points(address_keyword)
- 특정 장소(마트, 주민센터) 수거함 → search_collection_points(name_keyword)
- 주변/가까운 수거함 (좌표 있음) → get_nearby_collection_points(lat, lon)
- 주변 수거함 (지역명 있음, 좌표 없음) → geocode → get_nearby_collection_points

## 사용 금지 (DON'T)
- 분리배출 방법 질문 → 도구 사용 X
- 대형폐기물 수거 신청 → 도구 사용 X
- 재활용센터, 제로웨이스트샵 검색 → 도구 사용 X (다른 에이전트 담당)
- 일반 대화, 인사 → 도구 사용 X

# Tool 호출 순서 (Critical)

"[지역명] 수거함" 패턴:
1. search_collection_points(address_keyword="지역명")

"[장소] 수거함" 패턴:
1. search_collection_points(name_keyword="장소명")

"주변 수거함" 패턴 (user_location 있음):
1. get_nearby_collection_points(latitude=user_lat, longitude=user_lon)

"[지역명] 근처 수거함" 패턴 (user_location 없음):
1. geocode(place_name="지역명") → 좌표 획득
2. get_nearby_collection_points(latitude=결과lat, longitude=결과lon)

# 수거 품목 안내

이 수거함에서 수거하는 품목:
- 폐전자제품: 휴대폰, 노트북, 태블릿, 소형가전
- 폐건전지: AA, AAA, 리튬이온 배터리
- 폐형광등: 직관형, 원형, 컴팩트형

# 에러 처리

- 검색 결과 없음 → "해당 지역에서 수거함을 찾을 수 없습니다. 다른 지역을 검색해보세요."
- 좌표 없음 → "위치 정보가 필요합니다. 지역명을 알려주시거나 위치 권한을 허용해주세요."
- API 호출 실패 → "수거함 정보를 가져올 수 없습니다. 잠시 후 다시 시도해주세요."

# 응답 형식

수거함 정보:
1. 상호명 및 주소
2. 수거 가능 품목
3. 수거 비용 (무료/유료)
4. 거리 정보 (주변 검색 시)"""


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


class CollectionPointToolExecutor:
    """Collection Point API Tool 실행기."""

    def __init__(
        self,
        collection_point_client: "CollectionPointClientPort",
        kakao_client: "KakaoLocalClientPort | None" = None,
    ):
        self._client = collection_point_client
        self._kakao_client = kakao_client

    async def execute(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> ToolResult:
        """Tool 실행."""
        try:
            if tool_name == ToolName.SEARCH_COLLECTION_POINTS:
                return await self._search_collection_points(arguments)
            elif tool_name == ToolName.GET_NEARBY_COLLECTION_POINTS:
                return await self._get_nearby_collection_points(arguments)
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

    async def _search_collection_points(self, args: dict[str, Any]) -> ToolResult:
        """주소/상호명으로 수거함 검색."""
        address_keyword = args.get("address_keyword")
        name_keyword = args.get("name_keyword")

        if not address_keyword and not name_keyword:
            return ToolResult(
                tool_name=ToolName.SEARCH_COLLECTION_POINTS,
                success=False,
                error="주소(address_keyword) 또는 상호명(name_keyword) 중 하나 이상 필요합니다.",
            )

        response = await self._client.search_collection_points(
            address_keyword=address_keyword,
            name_keyword=name_keyword,
            page_size=10,
        )

        if not response.results:
            return ToolResult(
                tool_name=ToolName.SEARCH_COLLECTION_POINTS,
                success=False,
                error=f"검색 조건에 맞는 수거함을 찾을 수 없습니다.",
            )

        return ToolResult(
            tool_name=ToolName.SEARCH_COLLECTION_POINTS,
            success=True,
            data={
                "query": {
                    "address": address_keyword,
                    "name": name_keyword,
                },
                "total_count": response.total_count,
                "points": [
                    {
                        "id": p.id,
                        "name": p.name,
                        "address": p.address,
                        "collection_types": p.collection_types_text,
                        "collection_method": p.collection_method,
                        "fee": p.fee,
                        "is_free": p.is_free,
                        "place_category": p.place_category,
                    }
                    for p in response.results[:10]
                ],
            },
        )

    async def _get_nearby_collection_points(self, args: dict[str, Any]) -> ToolResult:
        """좌표 기반 주변 수거함 검색."""
        lat = args.get("latitude")
        lon = args.get("longitude")
        radius_km = args.get("radius_km", 2.0)

        if lat is None or lon is None:
            return ToolResult(
                tool_name=ToolName.GET_NEARBY_COLLECTION_POINTS,
                success=False,
                error="좌표(latitude, longitude)가 필수입니다.",
            )

        points = await self._client.get_nearby_collection_points(
            lat=lat,
            lon=lon,
            radius_km=min(radius_km, 5.0),  # 최대 5km
            limit=10,
        )

        if not points:
            return ToolResult(
                tool_name=ToolName.GET_NEARBY_COLLECTION_POINTS,
                success=False,
                error=f"반경 {radius_km}km 내에 수거함을 찾을 수 없습니다.",
            )

        return ToolResult(
            tool_name=ToolName.GET_NEARBY_COLLECTION_POINTS,
            success=True,
            data={
                "center": {"latitude": lat, "longitude": lon},
                "radius_km": radius_km,
                "count": len(points),
                "points": [
                    {
                        "id": p.id,
                        "name": p.name,
                        "address": p.address,
                        "collection_types": p.collection_types_text,
                        "fee": p.fee,
                        "is_free": p.is_free,
                        "lat": p.lat,
                        "lon": p.lon,
                    }
                    for p in points
                ],
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
    openai_client: Any,
    model: str,
    message: str,
    user_location: dict[str, float] | None,
    tool_executor: CollectionPointToolExecutor,
    max_iterations: int = 5,
) -> dict[str, Any]:
    """OpenAI Function Calling으로 Collection Point Agent 실행."""
    user_message = message
    if user_location:
        lat = user_location.get("latitude") or user_location.get("lat")
        lon = user_location.get("longitude") or user_location.get("lon")
        if lat and lon:
            user_message = f"{message}\n\n[현재 위치: 위도 {lat}, 경도 {lon}]"

    messages = [
        {"role": "system", "content": COLLECTION_POINT_AGENT_SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]

    all_tool_results: list[dict[str, Any]] = []

    for iteration in range(max_iterations):
        logger.debug(f"OpenAI collection point agent iteration {iteration + 1}")

        response = await openai_client.chat.completions.create(
            model=model,
            messages=messages,
            tools=OPENAI_TOOLS,
            tool_choice="auto",
        )

        assistant_message = response.choices[0].message

        if not assistant_message.tool_calls:
            return {
                "success": True,
                "summary": assistant_message.content,
                "tool_results": all_tool_results,
            }

        messages.append(assistant_message.model_dump())

        # 병렬 Tool 실행
        async def execute_tool(tc: Any) -> tuple[Any, dict, ToolResult]:
            tool_name = tc.function.name
            try:
                arguments = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                arguments = {}

            logger.info(
                "Executing collection point tool",
                extra={"tool": tool_name, "args": arguments},
            )
            result = await tool_executor.execute(tool_name, arguments)
            return tc, arguments, result

        execution_results = await asyncio.gather(
            *[execute_tool(tc) for tc in assistant_message.tool_calls]
        )

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

    return {
        "success": True,
        "summary": "수거함 정보를 처리했습니다.",
        "tool_results": all_tool_results,
    }


# ============================================================
# Gemini Function Calling Handler
# ============================================================


async def run_gemini_agent(
    gemini_client: Any,
    model: str,
    message: str,
    user_location: dict[str, float] | None,
    tool_executor: CollectionPointToolExecutor,
    max_iterations: int = 5,
) -> dict[str, Any]:
    """Gemini Function Calling으로 Collection Point Agent 실행."""
    from google.genai import types

    user_message = message
    if user_location:
        lat = user_location.get("latitude") or user_location.get("lat")
        lon = user_location.get("longitude") or user_location.get("lon")
        if lat and lon:
            user_message = f"{message}\n\n[현재 위치: 위도 {lat}, 경도 {lon}]"

    tools = types.Tool(function_declarations=GEMINI_TOOLS)
    config = types.GenerateContentConfig(
        tools=[tools],
        tool_config=types.ToolConfig(
            function_calling_config=types.FunctionCallingConfig(mode="AUTO"),
        ),
        system_instruction=COLLECTION_POINT_AGENT_SYSTEM_PROMPT,
        temperature=0,
    )

    contents = [user_message]
    all_tool_results: list[dict[str, Any]] = []

    for iteration in range(max_iterations):
        logger.debug(f"Gemini collection point agent iteration {iteration + 1}")

        response = await gemini_client.aio.models.generate_content(
            model=model,
            contents=contents,
            config=config,
        )

        candidate = response.candidates[0]
        parts = candidate.content.parts

        function_calls = [
            p for p in parts
            if hasattr(p, "function_call") and p.function_call is not None
        ]

        if not function_calls:
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
                "Executing collection point tool (Gemini)",
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

        contents.append(candidate.content)

        function_response_parts = [
            types.Part.from_function_response(
                name=r["_name"],
                response=r["_response"],
            )
            for r in results
        ]
        contents.append(types.Content(role="user", parts=function_response_parts))

    return {
        "success": True,
        "summary": "수거함 정보를 처리했습니다.",
        "tool_results": all_tool_results,
    }


# ============================================================
# Collection Point Agent Node Factory
# ============================================================


def create_collection_point_agent_node(
    collection_point_client: "CollectionPointClientPort",
    event_publisher: "ProgressNotifierPort",
    kakao_client: "KakaoLocalClientPort | None" = None,
    openai_client: Any | None = None,
    gemini_client: Any | None = None,
    default_model: str = "gpt-5.2",
    default_provider: str = "openai",
):
    """Collection Point Agent 노드 팩토리.

    LLM이 수거함 위치 API를 Tool로 사용하여 수거함 정보 제공.
    GPT-5.2 / Gemini 3 지원.

    Args:
        collection_point_client: 수거함 위치 클라이언트
        event_publisher: 이벤트 발행기
        kakao_client: Kakao Local API 클라이언트 (geocoding용)
        openai_client: OpenAI AsyncClient (선택)
        gemini_client: Gemini Client (선택)
        default_model: 기본 모델명
        default_provider: 기본 프로바이더

    Returns:
        collection_point_agent_node 함수
    """
    tool_executor = CollectionPointToolExecutor(
        collection_point_client=collection_point_client,
        kakao_client=kakao_client,
    )

    async def collection_point_agent_node(state: dict[str, Any]) -> dict[str, Any]:
        """LangGraph Collection Point Agent 노드."""
        job_id = state.get("job_id", "")
        message = state.get("message", "")
        user_location = state.get("user_location")

        await event_publisher.notify_stage(
            task_id=job_id,
            stage="collection_point",
            status="started",
            progress=45,
            message="수거함 위치 검색 중...",
        )

        try:
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
                logger.warning("No LLM client available for collection point agent")
                return {
                    "collection_point_context": create_error_context(
                        producer="collection_point",
                        job_id=job_id,
                        error="LLM 클라이언트가 없습니다.",
                    ),
                }

            # 결과에서 수거함 정보 추출
            points_info = None
            for tr in result.get("tool_results", []):
                if tr.get("success") and tr.get("tool") in [
                    "search_collection_points",
                    "get_nearby_collection_points",
                ]:
                    points_info = tr.get("result")
                    break

            if points_info:
                count = points_info.get("count") or len(points_info.get("points", []))
                await event_publisher.notify_stage(
                    task_id=job_id,
                    stage="collection_point",
                    status="completed",
                    progress=55,
                    result={"count": count},
                    message=f"{count}개 수거함 검색 완료",
                )

                return {
                    "collection_point_context": create_context(
                        data={
                            "found": True,
                            "points": points_info.get("points", []),
                            "total_count": points_info.get("total_count") or count,
                            "summary": result.get("summary"),
                            "context": result.get("summary"),
                        },
                        producer="collection_point",
                        job_id=job_id,
                    ),
                }
            else:
                await event_publisher.notify_stage(
                    task_id=job_id,
                    stage="collection_point",
                    status="completed",
                    progress=55,
                    message="수거함 검색 결과 없음",
                )

                return {
                    "collection_point_context": create_context(
                        data={
                            "found": False,
                            "points": [],
                            "summary": result.get("summary"),
                        },
                        producer="collection_point",
                        job_id=job_id,
                    ),
                }

        except Exception as e:
            logger.exception("Collection point agent failed")

            await event_publisher.notify_stage(
                task_id=job_id,
                stage="collection_point",
                status="failed",
                result={"error": str(e)},
            )

            return {
                "collection_point_context": create_error_context(
                    producer="collection_point",
                    job_id=job_id,
                    error=str(e),
                ),
            }

    return collection_point_agent_node


__all__ = [
    "create_collection_point_agent_node",
    "OPENAI_TOOLS",
    "GEMINI_TOOLS",
    "CollectionPointToolExecutor",
]
