"""Recyclable Price Agent Node - LLM with Price API Tools.

LLM이 재활용자원 가격 API를 Tool로 사용하여 시세 정보를 제공하는 에이전트 노드.

Architecture:
- LLM이 사용자 메시지를 분석하여 품목/카테고리/권역 추출
- Tool 실행 결과를 LLM이 해석하여 자연어 응답 생성
- OpenAI/Gemini 모두 지원 (Function Calling)

Tools:
- search_price: 품목명으로 가격 검색
- get_category_prices: 카테고리별 전체 가격 조회

Flow:
    Router → recyclable_price_agent → Answer
             └─ LLM analyzes message (extracts 품목, 권역)
             └─ LLM calls tools (Price API)
             └─ LLM generates price summary
             └─ Returns recyclable_price_context
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any

from chat_worker.application.ports.recyclable_price_client import (
    RecyclableCategory,
    RecyclableRegion,
    REGION_NAMES,
)
from chat_worker.infrastructure.orchestration.langgraph.context_helper import (
    create_context,
    create_error_context,
)

if TYPE_CHECKING:
    from chat_worker.application.ports.events import ProgressNotifierPort
    from chat_worker.application.ports.recyclable_price_client import (
        RecyclablePriceClientPort,
    )

logger = logging.getLogger(__name__)


# ============================================================
# Tool Definitions
# ============================================================


class ToolName(str, Enum):
    """사용 가능한 Tool 이름."""

    SEARCH_PRICE = "search_price"
    GET_CATEGORY_PRICES = "get_category_prices"


# ============================================================
# OpenAI Function Calling Tools (GPT-5.2 Strict Mode)
# ============================================================

OPENAI_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_price",
            "description": (
                "재활용자원 품목명으로 가격 검색. "
                "사용 시점: 사용자가 '캔 가격', '신문지 시세', '페트병 얼마야?' 등 "
                "특정 품목의 가격을 물을 때 호출. "
                "반환값: 품목별 kg당 가격, 권역별 가격, 조사일. "
                "주의: 부분 매칭 지원 (예: '캔' → '알루미늄캔', '철캔' 모두 반환)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "item_name": {
                        "type": "string",
                        "description": (
                            "검색할 품목명. 필수. "
                            "예: '캔', '신문지', '페트병', '골판지', '비닐', '고철'. "
                            "가능한 일반적인 명칭 사용."
                        ),
                    },
                    "region": {
                        "type": "string",
                        "enum": [
                            "capital", "gangwon", "chungbuk", "chungnam",
                            "jeonbuk", "jeonnam", "gyeongbuk", "gyeongnam", "national",
                        ],
                        "description": (
                            "권역. 선택. "
                            "capital=수도권, gangwon=강원, chungbuk=충북, chungnam=충남, "
                            "jeonbuk=전북, jeonnam=전남, gyeongbuk=경북, gyeongnam=경남, "
                            "national=전국평균(기본값)."
                        ),
                    },
                },
                "required": ["item_name"],
                "additionalProperties": False,
            },
            "strict": True,
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_category_prices",
            "description": (
                "카테고리별 전체 재활용자원 가격 조회. "
                "사용 시점: 사용자가 '폐지 가격 전체', '플라스틱 시세', '금속류 가격' 등 "
                "카테고리 전체 가격을 물을 때 호출. "
                "반환값: 해당 카테고리의 모든 품목과 가격."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "enum": ["paper", "plastic", "glass", "metal", "tire"],
                        "description": (
                            "카테고리. 필수. "
                            "paper=폐지, plastic=폐플라스틱, glass=폐유리병, "
                            "metal=폐금속, tire=폐타이어."
                        ),
                    },
                    "region": {
                        "type": "string",
                        "enum": [
                            "capital", "gangwon", "chungbuk", "chungnam",
                            "jeonbuk", "jeonnam", "gyeongbuk", "gyeongnam", "national",
                        ],
                        "description": "권역. 선택. 기본값: national(전국평균).",
                    },
                },
                "required": ["category"],
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
        "name": "search_price",
        "description": (
            "재활용자원 품목명으로 가격 검색. "
            "사용 시점: 사용자가 특정 품목의 가격을 물을 때 호출. "
            "반환값: 품목별 kg당 가격, 권역별 가격, 조사일. "
            "부분 매칭 지원 (예: '캔' → '알루미늄캔', '철캔' 모두 반환)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "item_name": {
                    "type": "string",
                    "description": "검색할 품목명. 필수. 예: '캔', '신문지', '페트병'.",
                },
                "region": {
                    "type": "string",
                    "enum": [
                        "capital", "gangwon", "chungbuk", "chungnam",
                        "jeonbuk", "jeonnam", "gyeongbuk", "gyeongnam", "national",
                    ],
                    "description": "권역. 선택. 기본값: national(전국평균).",
                },
            },
            "required": ["item_name"],
        },
    },
    {
        "name": "get_category_prices",
        "description": (
            "카테고리별 전체 재활용자원 가격 조회. "
            "사용 시점: 사용자가 카테고리 전체 가격을 물을 때 호출. "
            "반환값: 해당 카테고리의 모든 품목과 가격."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "enum": ["paper", "plastic", "glass", "metal", "tire"],
                    "description": "카테고리. 필수. paper=폐지, plastic=폐플라스틱, glass=폐유리병, metal=폐금속, tire=폐타이어.",
                },
                "region": {
                    "type": "string",
                    "enum": [
                        "capital", "gangwon", "chungbuk", "chungnam",
                        "jeonbuk", "jeonnam", "gyeongbuk", "gyeongnam", "national",
                    ],
                    "description": "권역. 선택. 기본값: national(전국평균).",
                },
            },
            "required": ["category"],
        },
    },
]

# ============================================================
# System Prompt for Recyclable Price Agent
# ============================================================

RECYCLABLE_PRICE_AGENT_SYSTEM_PROMPT = """# Context
당신은 Eco² 앱의 재활용자원 시세 정보 에이전트입니다.
사용자에게 재활용품의 kg당 가격과 시세 정보를 제공합니다.

# Scope Discipline
이 에이전트는 search_price, get_category_prices 도구만 사용합니다.
다른 작업(날씨, 장소 검색, 대형폐기물 등)은 도구 없이 직접 응답하세요.
절대로 정의되지 않은 도구를 호출하거나 새로운 작업을 만들어내지 마세요.

# Preambles (GPT-5.2)
도구를 호출하기 전에, 왜 그 도구를 호출하는지 간단히 설명하세요.
예: "캔의 현재 시세를 조회하기 위해 search_price를 호출합니다."

# Tool 사용 규칙

## 사용 시점 (DO)
- 특정 품목 가격 질문 → search_price(item_name)
- 카테고리 전체 가격 질문 → get_category_prices(category)
- 권역별 가격 비교 질문 → search_price 또는 get_category_prices (region 파라미터)

## 사용 금지 (DON'T)
- 분리배출 방법 질문 → 도구 사용 X
- 대형폐기물 수수료 → 도구 사용 X (다른 에이전트 담당)
- 일반 대화, 인사 → 도구 사용 X

# 품목/카테고리 매핑

품목명 추출 예시:
- "캔 가격" → item_name="캔"
- "신문지 시세" → item_name="신문지"
- "페트병 얼마야?" → item_name="페트병"
- "알루미늄 가격" → item_name="알루미늄"

카테고리 매핑:
- 폐지, 종이, 신문지, 골판지 → category="paper"
- 플라스틱, 페트병, 비닐 → category="plastic"
- 유리병, 병 → category="glass"
- 금속, 철, 알루미늄, 캔, 고철 → category="metal"
- 타이어 → category="tire"

권역 매핑:
- 서울, 경기, 인천 → region="capital"
- 강원 → region="gangwon"
- 충북, 충청북도 → region="chungbuk"
- 충남, 충청남도, 대전, 세종 → region="chungnam"
- 전북, 전라북도 → region="jeonbuk"
- 전남, 전라남도, 광주 → region="jeonnam"
- 경북, 경상북도, 대구 → region="gyeongbuk"
- 경남, 경상남도, 부산, 울산 → region="gyeongnam"
- 전국, 평균 → region="national" (기본값)

# 에러 처리

- 검색 결과 없음 → "해당 품목의 가격 정보를 찾을 수 없습니다."
- API 호출 실패 → "가격 정보를 가져올 수 없습니다. 잠시 후 다시 시도해주세요."

# 응답 형식

가격 정보:
1. 품목명과 kg당 가격
2. 조사 기준일 (YYYY년 MM월)
3. 권역 정보 (해당 시)
4. 형태별 가격 차이 설명 (압축, 플레이크 등)"""


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


class RecyclablePriceToolExecutor:
    """Recyclable Price API Tool 실행기."""

    def __init__(self, price_client: "RecyclablePriceClientPort"):
        self._client = price_client

    async def execute(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> ToolResult:
        """Tool 실행."""
        try:
            if tool_name == ToolName.SEARCH_PRICE:
                return await self._search_price(arguments)
            elif tool_name == ToolName.GET_CATEGORY_PRICES:
                return await self._get_category_prices(arguments)
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

    async def _search_price(self, args: dict[str, Any]) -> ToolResult:
        """품목명으로 가격 검색."""
        item_name = args.get("item_name")
        region_str = args.get("region")

        if not item_name:
            return ToolResult(
                tool_name=ToolName.SEARCH_PRICE,
                success=False,
                error="품목명(item_name)이 필수입니다.",
            )

        # 권역 변환
        region = None
        if region_str:
            try:
                region = RecyclableRegion(region_str)
            except ValueError:
                pass  # 기본값 사용

        response = await self._client.search_price(item_name, region)

        if not response.has_results:
            return ToolResult(
                tool_name=ToolName.SEARCH_PRICE,
                success=False,
                error=f"'{item_name}' 품목의 가격 정보를 찾을 수 없습니다.",
            )

        return ToolResult(
            tool_name=ToolName.SEARCH_PRICE,
            success=True,
            data={
                "query": item_name,
                "region": REGION_NAMES.get(region, "전국") if region else "전국",
                "survey_date": response.survey_date,
                "item_count": response.total_count,
                "items": [
                    {
                        "item_name": item.item_name,
                        "display_name": item.display_name,
                        "category": item.category.value,
                        "price_per_kg": item.price_per_kg,
                        "price_text": item.price_text,
                        "form": item.form,
                        "note": item.note,
                    }
                    for item in response.items[:10]
                ],
            },
        )

    async def _get_category_prices(self, args: dict[str, Any]) -> ToolResult:
        """카테고리별 전체 가격 조회."""
        category_str = args.get("category")
        region_str = args.get("region")

        if not category_str:
            return ToolResult(
                tool_name=ToolName.GET_CATEGORY_PRICES,
                success=False,
                error="카테고리(category)가 필수입니다.",
            )

        # 카테고리 변환
        try:
            category = RecyclableCategory(category_str)
        except ValueError:
            return ToolResult(
                tool_name=ToolName.GET_CATEGORY_PRICES,
                success=False,
                error=f"알 수 없는 카테고리: {category_str}",
            )

        # 권역 변환
        region = None
        if region_str:
            try:
                region = RecyclableRegion(region_str)
            except ValueError:
                pass

        response = await self._client.get_category_prices(category, region)

        if not response.has_results:
            return ToolResult(
                tool_name=ToolName.GET_CATEGORY_PRICES,
                success=False,
                error=f"'{category_str}' 카테고리의 가격 정보를 찾을 수 없습니다.",
            )

        return ToolResult(
            tool_name=ToolName.GET_CATEGORY_PRICES,
            success=True,
            data={
                "category": category_str,
                "region": REGION_NAMES.get(region, "전국") if region else "전국",
                "survey_date": response.survey_date,
                "item_count": response.total_count,
                "items": [
                    {
                        "item_name": item.item_name,
                        "display_name": item.display_name,
                        "price_per_kg": item.price_per_kg,
                        "price_text": item.price_text,
                        "form": item.form,
                    }
                    for item in response.items[:15]
                ],
            },
        )


# ============================================================
# OpenAI Function Calling Handler
# ============================================================


async def run_openai_agent(
    openai_client: Any,
    model: str,
    message: str,
    tool_executor: RecyclablePriceToolExecutor,
    max_iterations: int = 5,
) -> dict[str, Any]:
    """OpenAI Function Calling으로 Recyclable Price Agent 실행."""
    messages = [
        {"role": "system", "content": RECYCLABLE_PRICE_AGENT_SYSTEM_PROMPT},
        {"role": "user", "content": message},
    ]

    all_tool_results: list[dict[str, Any]] = []

    for iteration in range(max_iterations):
        logger.debug(f"OpenAI recyclable price agent iteration {iteration + 1}")

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
                "Executing recyclable price tool",
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
        "summary": "재활용자원 가격 정보를 처리했습니다.",
        "tool_results": all_tool_results,
    }


# ============================================================
# Gemini Function Calling Handler
# ============================================================


async def run_gemini_agent(
    gemini_client: Any,
    model: str,
    message: str,
    tool_executor: RecyclablePriceToolExecutor,
    max_iterations: int = 5,
) -> dict[str, Any]:
    """Gemini Function Calling으로 Recyclable Price Agent 실행."""
    from google.genai import types

    tools = types.Tool(function_declarations=GEMINI_TOOLS)
    config = types.GenerateContentConfig(
        tools=[tools],
        tool_config=types.ToolConfig(
            function_calling_config=types.FunctionCallingConfig(mode="AUTO"),
        ),
        system_instruction=RECYCLABLE_PRICE_AGENT_SYSTEM_PROMPT,
        temperature=0,
    )

    contents = [message]
    all_tool_results: list[dict[str, Any]] = []

    for iteration in range(max_iterations):
        logger.debug(f"Gemini recyclable price agent iteration {iteration + 1}")

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
                "Executing recyclable price tool (Gemini)",
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
        "summary": "재활용자원 가격 정보를 처리했습니다.",
        "tool_results": all_tool_results,
    }


# ============================================================
# Recyclable Price Agent Node Factory
# ============================================================


def create_recyclable_price_agent_node(
    price_client: "RecyclablePriceClientPort",
    event_publisher: "ProgressNotifierPort",
    openai_client: Any | None = None,
    gemini_client: Any | None = None,
    default_model: str = "gpt-5.2",
    default_provider: str = "openai",
):
    """Recyclable Price Agent 노드 팩토리.

    LLM이 재활용자원 가격 API를 Tool로 사용하여 시세 정보 제공.
    GPT-5.2 / Gemini 3 지원.

    Args:
        price_client: 재활용자원 가격 클라이언트
        event_publisher: 이벤트 발행기
        openai_client: OpenAI AsyncClient (선택)
        gemini_client: Gemini Client (선택)
        default_model: 기본 모델명
        default_provider: 기본 프로바이더

    Returns:
        recyclable_price_agent_node 함수
    """
    tool_executor = RecyclablePriceToolExecutor(price_client)

    async def recyclable_price_agent_node(state: dict[str, Any]) -> dict[str, Any]:
        """LangGraph Recyclable Price Agent 노드."""
        job_id = state.get("job_id", "")
        message = state.get("message", "")

        await event_publisher.notify_stage(
            task_id=job_id,
            stage="recyclable_price",
            status="started",
            progress=45,
            message="재활용자원 시세 조회 중...",
        )

        try:
            provider = state.get("llm_provider", default_provider)
            model = state.get("llm_model", default_model)

            if provider == "gemini" and gemini_client is not None:
                result = await run_gemini_agent(
                    gemini_client=gemini_client,
                    model=model,
                    message=message,
                    tool_executor=tool_executor,
                )
            elif openai_client is not None:
                result = await run_openai_agent(
                    openai_client=openai_client,
                    model=model,
                    message=message,
                    tool_executor=tool_executor,
                )
            else:
                logger.warning("No LLM client available for recyclable price agent")
                return {
                    "recyclable_price_context": create_error_context(
                        producer="recyclable_price",
                        job_id=job_id,
                        error="LLM 클라이언트가 없습니다.",
                    ),
                }

            # 결과에서 가격 정보 추출
            price_info = None
            for tr in result.get("tool_results", []):
                if tr.get("success"):
                    price_info = tr.get("result")
                    break

            if price_info:
                item_count = price_info.get("item_count", 0)
                await event_publisher.notify_stage(
                    task_id=job_id,
                    stage="recyclable_price",
                    status="completed",
                    progress=55,
                    result={"item_count": item_count},
                    message=f"{item_count}개 품목 시세 조회 완료",
                )

                return {
                    "recyclable_price_context": create_context(
                        data={
                            "prices": price_info,
                            "summary": result.get("summary"),
                            "context": result.get("summary"),
                        },
                        producer="recyclable_price",
                        job_id=job_id,
                    ),
                }
            else:
                await event_publisher.notify_stage(
                    task_id=job_id,
                    stage="recyclable_price",
                    status="completed",
                    progress=55,
                    message="시세 정보 없음",
                )

                return {
                    "recyclable_price_context": create_context(
                        data={
                            "prices": None,
                            "summary": result.get("summary"),
                        },
                        producer="recyclable_price",
                        job_id=job_id,
                    ),
                }

        except Exception as e:
            logger.exception("Recyclable price agent failed")

            await event_publisher.notify_stage(
                task_id=job_id,
                stage="recyclable_price",
                status="failed",
                result={"error": str(e)},
            )

            return {
                "recyclable_price_context": create_error_context(
                    producer="recyclable_price",
                    job_id=job_id,
                    error=str(e),
                ),
            }

    return recyclable_price_agent_node


__all__ = [
    "create_recyclable_price_agent_node",
    "OPENAI_TOOLS",
    "GEMINI_TOOLS",
    "RecyclablePriceToolExecutor",
]
