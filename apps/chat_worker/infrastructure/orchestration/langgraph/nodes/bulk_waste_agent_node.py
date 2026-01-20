"""Bulk Waste Agent Node - LLM with Bulk Waste API Tools.

LLM이 대형폐기물 API를 Tool로 사용하여 수거 정보를 제공하는 에이전트 노드.

Architecture:
- LLM이 사용자 메시지를 분석하여 지역/품목 추출
- Tool 실행 결과를 LLM이 해석하여 자연어 응답 생성
- OpenAI/Gemini 모두 지원 (Function Calling)

Tools:
- get_collection_info: 지역별 대형폐기물 수거 방법 조회
- search_fee: 품목별 수수료 검색

Flow:
    Router → bulk_waste_agent → Answer
             └─ LLM analyzes message (extracts 지역, 품목)
             └─ LLM calls tools (Bulk Waste API)
             └─ LLM generates response with collection/fee info
             └─ Returns bulk_waste_context
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
    from chat_worker.application.ports.bulk_waste_client import BulkWasteClientPort
    from chat_worker.application.ports.events import ProgressNotifierPort

logger = logging.getLogger(__name__)


# ============================================================
# Tool Definitions
# ============================================================


class ToolName(str, Enum):
    """사용 가능한 Tool 이름."""

    GET_COLLECTION_INFO = "get_collection_info"
    SEARCH_FEE = "search_fee"


# ============================================================
# OpenAI Function Calling Tools (GPT-5.2 Strict Mode)
# ============================================================

OPENAI_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_collection_info",
            "description": (
                "지역별 대형폐기물 수거 방법 조회. "
                "사용 시점: 사용자가 '대형폐기물 어떻게 버려요?', '수거 신청 어떻게 해요?' 등 "
                "수거 방법이나 신청 절차를 물을 때 호출. "
                "반환값: 신청 URL, 전화번호, 수거 방식, 수수료 납부 방법. "
                "주의: 시군구명이 필수. 사용자가 '강남구 대형폐기물'이라고 하면 sigungu='강남구' 전달."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "sigungu": {
                        "type": "string",
                        "description": (
                            "시군구명. 필수. "
                            "예: '강남구', '성동구', '해운대구', '수원시 영통구'. "
                            "서울은 '구' 단위, 경기는 '시' 또는 '시 구' 단위."
                        ),
                    },
                },
                "required": ["sigungu"],
                "additionalProperties": False,
            },
            "strict": True,
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_fee",
            "description": (
                "대형폐기물 품목별 수수료 검색. "
                "사용 시점: 사용자가 '소파 버리는 비용', '냉장고 수수료', '침대 얼마야?' 등 "
                "특정 품목의 수수료를 물을 때 호출. "
                "반환값: 매칭되는 품목 목록과 각 수수료. "
                "주의: sigungu와 item_name 모두 필수. 지역마다 수수료가 다름."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "sigungu": {
                        "type": "string",
                        "description": (
                            "시군구명. 필수. "
                            "예: '강남구', '성동구', '해운대구'."
                        ),
                    },
                    "item_name": {
                        "type": "string",
                        "description": (
                            "검색할 품목명. 필수. "
                            "예: '소파', '냉장고', '침대', '장롱', '세탁기'. "
                            "부분 매칭 지원 (예: '소파' → '소파(2인용)', '소파(3인용)' 모두 반환)."
                        ),
                    },
                },
                "required": ["sigungu", "item_name"],
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
        "name": "get_collection_info",
        "description": (
            "지역별 대형폐기물 수거 방법 조회. "
            "사용 시점: 사용자가 대형폐기물 수거/신청 방법을 물을 때 호출. "
            "반환값: 신청 URL, 전화번호, 수거 방식, 수수료 납부 방법. "
            "주의: 시군구명 필수. '강남구 대형폐기물'이면 sigungu='강남구' 전달."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "sigungu": {
                    "type": "string",
                    "description": "시군구명. 필수. 예: '강남구', '성동구', '해운대구'.",
                },
            },
            "required": ["sigungu"],
        },
    },
    {
        "name": "search_fee",
        "description": (
            "대형폐기물 품목별 수수료 검색. "
            "사용 시점: 사용자가 특정 품목의 수수료를 물을 때 호출. "
            "반환값: 매칭되는 품목 목록과 각 수수료. "
            "주의: sigungu와 item_name 모두 필수. 지역마다 수수료가 다름."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "sigungu": {
                    "type": "string",
                    "description": "시군구명. 필수. 예: '강남구', '성동구'.",
                },
                "item_name": {
                    "type": "string",
                    "description": "검색할 품목명. 필수. 예: '소파', '냉장고', '침대'.",
                },
            },
            "required": ["sigungu", "item_name"],
        },
    },
]

# ============================================================
# System Prompt for Bulk Waste Agent
# ============================================================

BULK_WASTE_AGENT_SYSTEM_PROMPT = """# Context
당신은 Eco² 앱의 대형폐기물 정보 에이전트입니다.
사용자에게 대형폐기물 수거 신청 방법과 품목별 수수료 정보를 제공합니다.

# Scope Discipline
이 에이전트는 get_collection_info, search_fee 도구만 사용합니다.
다른 작업(날씨, 장소 검색, 일반 분리배출 방법 등)은 도구 없이 직접 응답하세요.
절대로 정의되지 않은 도구를 호출하거나 새로운 작업을 만들어내지 마세요.

# Preambles (GPT-5.2)
도구를 호출하기 전에, 왜 그 도구를 호출하는지 간단히 설명하세요.
예: "강남구의 대형폐기물 수거 방법을 조회하기 위해 get_collection_info를 호출합니다."

# Tool 사용 규칙

## 사용 시점 (DO)
- 대형폐기물 수거/신청 방법 질문 → get_collection_info(sigungu)
- 품목별 수수료 질문 → search_fee(sigungu, item_name)
- 수거 방법 + 수수료 모두 질문 → get_collection_info + search_fee 둘 다 호출

## 사용 금지 (DON'T)
- 일반 분리배출 방법 (플라스틱, 종이 등) → 도구 사용 X
- 일반 대화, 인사 → 도구 사용 X
- 날씨, 장소 검색 → 도구 사용 X (범위 밖)

# 지역 추출 규칙

사용자 메시지에서 지역명 추출:
- "강남구 대형폐기물" → sigungu="강남구"
- "성동구에서 소파 버리려면" → sigungu="성동구"
- "서울시 마포구" → sigungu="마포구"
- "수원시 영통구" → sigungu="수원시 영통구"

지역명이 없으면:
- 도구 호출하지 않고 "지역(구)을 알려주세요" 요청

# 품목 추출 규칙

사용자 메시지에서 품목명 추출:
- "소파 버리는 비용" → item_name="소파"
- "냉장고 수수료" → item_name="냉장고"
- "침대 얼마야?" → item_name="침대"
- "3인용 소파" → item_name="소파" (크기는 검색 결과에서 구분)

# 에러 처리

- 지역 정보 없음 → "대형폐기물 수거 정보는 지역마다 다릅니다. 지역(구)을 알려주세요."
- 품목 검색 결과 없음 → "해당 품목을 찾을 수 없습니다. 다른 이름으로 검색해보세요."
- API 호출 실패 → "정보를 가져올 수 없습니다. 잠시 후 다시 시도해주세요."

# 응답 형식

수거 방법 정보:
1. 신청 방법 (URL 또는 전화번호)
2. 수거 방식 설명
3. 수수료 납부 방법

수수료 정보:
1. 품목명과 크기별 수수료 목록
2. 가장 일반적인 크기 강조
3. 비고사항 포함 (있으면)"""


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


class BulkWasteToolExecutor:
    """Bulk Waste API Tool 실행기."""

    def __init__(self, bulk_waste_client: "BulkWasteClientPort"):
        self._client = bulk_waste_client

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
            if tool_name == ToolName.GET_COLLECTION_INFO:
                return await self._get_collection_info(arguments)
            elif tool_name == ToolName.SEARCH_FEE:
                return await self._search_fee(arguments)
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

    async def _get_collection_info(self, args: dict[str, Any]) -> ToolResult:
        """대형폐기물 수거 방법 조회."""
        sigungu = args.get("sigungu")

        if not sigungu:
            return ToolResult(
                tool_name=ToolName.GET_COLLECTION_INFO,
                success=False,
                error="시군구명(sigungu)이 필수입니다.",
            )

        info = await self._client.get_bulk_waste_info(sigungu)

        if info is None:
            return ToolResult(
                tool_name=ToolName.GET_COLLECTION_INFO,
                success=False,
                error=f"'{sigungu}' 지역의 대형폐기물 수거 정보를 찾을 수 없습니다.",
            )

        return ToolResult(
            tool_name=ToolName.GET_COLLECTION_INFO,
            success=True,
            data={
                "sigungu": info.sigungu,
                "application_url": info.application_url,
                "application_phone": info.application_phone,
                "collection_method": info.collection_method,
                "fee_payment_method": info.fee_payment_method,
                "item_count": len(info.items) if info.items else 0,
            },
        )

    async def _search_fee(self, args: dict[str, Any]) -> ToolResult:
        """품목별 수수료 검색."""
        sigungu = args.get("sigungu")
        item_name = args.get("item_name")

        if not sigungu:
            return ToolResult(
                tool_name=ToolName.SEARCH_FEE,
                success=False,
                error="시군구명(sigungu)이 필수입니다.",
            )

        if not item_name:
            return ToolResult(
                tool_name=ToolName.SEARCH_FEE,
                success=False,
                error="품목명(item_name)이 필수입니다.",
            )

        items = await self._client.search_bulk_waste_fee(sigungu, item_name)

        if not items:
            return ToolResult(
                tool_name=ToolName.SEARCH_FEE,
                success=False,
                error=f"'{sigungu}'에서 '{item_name}' 품목을 찾을 수 없습니다.",
            )

        return ToolResult(
            tool_name=ToolName.SEARCH_FEE,
            success=True,
            data={
                "sigungu": sigungu,
                "search_query": item_name,
                "item_count": len(items),
                "items": [
                    {
                        "item_name": item.item_name,
                        "category": item.category,
                        "fee": item.fee,
                        "fee_text": item.fee_text,
                        "size_info": item.size_info,
                        "note": item.note,
                    }
                    for item in items[:10]  # 최대 10개
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
    tool_executor: BulkWasteToolExecutor,
    max_iterations: int = 5,
) -> dict[str, Any]:
    """OpenAI Function Calling으로 Bulk Waste Agent 실행."""
    messages = [
        {"role": "system", "content": BULK_WASTE_AGENT_SYSTEM_PROMPT},
        {"role": "user", "content": message},
    ]

    all_tool_results: list[dict[str, Any]] = []

    for iteration in range(max_iterations):
        logger.debug(f"OpenAI bulk waste agent iteration {iteration + 1}")

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
                "Executing bulk waste tool",
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
        "summary": "대형폐기물 정보를 처리했습니다.",
        "tool_results": all_tool_results,
    }


# ============================================================
# Gemini Function Calling Handler
# ============================================================


async def run_gemini_agent(
    gemini_client: Any,
    model: str,
    message: str,
    tool_executor: BulkWasteToolExecutor,
    max_iterations: int = 5,
) -> dict[str, Any]:
    """Gemini Function Calling으로 Bulk Waste Agent 실행."""
    from google.genai import types

    tools = types.Tool(function_declarations=GEMINI_TOOLS)
    config = types.GenerateContentConfig(
        tools=[tools],
        tool_config=types.ToolConfig(
            function_calling_config=types.FunctionCallingConfig(mode="AUTO"),
        ),
        system_instruction=BULK_WASTE_AGENT_SYSTEM_PROMPT,
        temperature=0,
    )

    contents = [message]
    all_tool_results: list[dict[str, Any]] = []

    for iteration in range(max_iterations):
        logger.debug(f"Gemini bulk waste agent iteration {iteration + 1}")

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
                "Executing bulk waste tool (Gemini)",
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
        "summary": "대형폐기물 정보를 처리했습니다.",
        "tool_results": all_tool_results,
    }


# ============================================================
# Bulk Waste Agent Node Factory
# ============================================================


def create_bulk_waste_agent_node(
    bulk_waste_client: "BulkWasteClientPort",
    event_publisher: "ProgressNotifierPort",
    openai_client: Any | None = None,
    gemini_client: Any | None = None,
    default_model: str = "gpt-5.2",
    default_provider: str = "openai",
):
    """Bulk Waste Agent 노드 팩토리.

    LLM이 대형폐기물 API를 Tool로 사용하여 수거/수수료 정보 제공.
    GPT-5.2 / Gemini 3 지원.

    Args:
        bulk_waste_client: 대형폐기물 클라이언트
        event_publisher: 이벤트 발행기
        openai_client: OpenAI AsyncClient (선택)
        gemini_client: Gemini Client (선택)
        default_model: 기본 모델명
        default_provider: 기본 프로바이더

    Returns:
        bulk_waste_agent_node 함수
    """
    tool_executor = BulkWasteToolExecutor(bulk_waste_client)

    async def bulk_waste_agent_node(state: dict[str, Any]) -> dict[str, Any]:
        """LangGraph Bulk Waste Agent 노드."""
        job_id = state.get("job_id", "")
        message = state.get("message", "")

        await event_publisher.notify_stage(
            task_id=job_id,
            stage="bulk_waste",
            status="started",
            progress=45,
            message="대형폐기물 정보 조회 중...",
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
                # Fallback: LLM 없으면 에러
                logger.warning("No LLM client available for bulk waste agent")
                return {
                    "bulk_waste_context": create_error_context(
                        producer="bulk_waste",
                        job_id=job_id,
                        error="LLM 클라이언트가 없습니다.",
                    ),
                }

            # 결과에서 정보 추출
            collection_info = None
            fee_info = None
            for tr in result.get("tool_results", []):
                if tr.get("success"):
                    if tr.get("tool") == "get_collection_info":
                        collection_info = tr.get("result")
                    elif tr.get("tool") == "search_fee":
                        fee_info = tr.get("result")

            has_collection = collection_info is not None
            has_fees = fee_info is not None

            # Progress: 완료
            if has_collection or has_fees:
                result_message = "대형폐기물 정보 조회 완료"
                if has_collection and has_fees:
                    result_message = "수거 방법 및 수수료 정보 조회 완료"
                elif has_collection:
                    result_message = "대형폐기물 수거 방법 조회 완료"
                elif has_fees:
                    fee_count = fee_info.get("item_count", 0) if fee_info else 0
                    result_message = f"{fee_count}개 품목 수수료 조회 완료"

                await event_publisher.notify_stage(
                    task_id=job_id,
                    stage="bulk_waste",
                    status="completed",
                    progress=55,
                    result={
                        "has_collection": has_collection,
                        "has_fees": has_fees,
                    },
                    message=result_message,
                )

                context_data = {
                    "collection": collection_info,
                    "fees": fee_info,
                    "summary": result.get("summary"),
                    "context": result.get("summary"),
                }

                return {
                    "bulk_waste_context": create_context(
                        data=context_data,
                        producer="bulk_waste",
                        job_id=job_id,
                    ),
                }
            else:
                # 정보 없음 (지역명 추출 실패 등)
                await event_publisher.notify_stage(
                    task_id=job_id,
                    stage="bulk_waste",
                    status="waiting",
                    message="지역 정보 필요",
                )

                return {
                    "bulk_waste_context": create_context(
                        data={
                            "needs_location": True,
                            "summary": result.get("summary"),
                        },
                        producer="bulk_waste",
                        job_id=job_id,
                    ),
                }

        except Exception as e:
            logger.exception("Bulk waste agent failed")

            await event_publisher.notify_stage(
                task_id=job_id,
                stage="bulk_waste",
                status="failed",
                result={"error": str(e)},
            )

            return {
                "bulk_waste_context": create_error_context(
                    producer="bulk_waste",
                    job_id=job_id,
                    error=str(e),
                ),
            }

    return bulk_waste_agent_node


__all__ = [
    "create_bulk_waste_agent_node",
    "OPENAI_TOOLS",
    "GEMINI_TOOLS",
    "BulkWasteToolExecutor",
]
