"""Web Search Node - LangGraph 어댑터.

얇은 어댑터: state 변환 + LLM 도구 호출 + context 저장.

Clean Architecture:
- Node(Adapter): 이 파일 - LangGraph glue code
- LLM: generate_with_tools() - 네이티브 웹 검색 (OpenAI/Gemini)

Production Architecture:
- NodeExecutor로 Policy 적용 (timeout, retry, circuit breaker)
- web_search 노드는 FAIL_OPEN (보조 정보, 없어도 답변 가능)

Dual Mode (weather_node 패턴):
1. Standalone: intent="web_search" → 무조건 검색 수행
2. Enrichment: 다른 intent의 보조 → Router가 이미 결정, Agents SDK가 검색 수행

Channel Separation:
- 출력 채널: web_search_results
- Reducer: priority_preemptive_reducer
- spread 금지: {"web_search_results": create_context(...)} 형태로 반환

Native Web Search:
- OpenAI: Responses API web_search tool
- Gemini: Google Search Grounding
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

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

logger = logging.getLogger(__name__)

# 웹 검색 시스템 프롬프트 (Agents SDK WebSearchTool + Responses API 공용)
WEB_SEARCH_SYSTEM_PROMPT = """당신은 웹 검색 결과를 바탕으로 정확하고 유용한 정보를 제공하는 도우미입니다.

## 규칙
1. 검색 결과를 바탕으로 사실에 기반한 답변을 제공하세요.
2. 출처가 불분명한 정보는 제외하세요.
3. 최신 정보를 우선하여 답변하세요.
4. 답변은 간결하고 핵심적으로 작성하세요.
5. 관련 정보가 없으면 솔직하게 안내하세요.
"""


def create_web_search_node(
    llm: "LLMClientPort",
    event_publisher: "ProgressNotifierPort | None" = None,
):
    """웹 검색 노드 팩토리.

    Dual Mode:
    - Standalone (intent="web_search"): 무조건 검색 수행
    - Enrichment (other intents): Router가 이미 결정, Agents SDK가 네이티브 검색 수행

    검색 필요 여부는 dynamic_router의 ConditionalEnrichment가 판단:
    - general + 낮은 confidence → 검색 필요
    - 비-general + 실시간 키워드 → 검색 필요

    Agents SDK WebSearchTool이 실제 검색을 수행하며,
    불필요한 generate_function_call 호출 없이 1회 API 호출로 완료.

    Args:
        llm: LLM 클라이언트 (generate_with_tools 지원)
        event_publisher: 이벤트 발행자 (진행 상황 알림용)

    Returns:
        web_search_node 함수
    """

    async def _execute_web_search(
        message: str,
        job_id: str,
        max_result_chars: int = 50_000,
    ) -> str | None:
        """네이티브 웹 검색 실행.

        Args:
            message: 검색 쿼리
            job_id: 작업 ID
            max_result_chars: 결과 최대 문자 수 (기본 50K chars ≈ 12.5K tokens)
        """
        result_parts: list[str] = []

        try:
            async for chunk in llm.generate_with_tools(
                prompt=message,
                tools=["web_search"],
                system_prompt=WEB_SEARCH_SYSTEM_PROMPT,
            ):
                if chunk:
                    result_parts.append(chunk)
        except Exception as e:
            logger.error(
                "Web search execution failed",
                extra={"job_id": job_id, "error": str(e)},
            )
            return None

        result = "".join(result_parts)
        if not result.strip():
            return None

        if len(result) > max_result_chars:
            logger.warning(
                "Web search result truncated",
                extra={
                    "job_id": job_id,
                    "original_chars": len(result),
                    "truncated_to": max_result_chars,
                },
            )
            result = result[:max_result_chars]

        return result

    async def _web_search_node_inner(state: dict[str, Any]) -> dict[str, Any]:
        """실제 노드 로직 (NodeExecutor가 래핑)."""
        job_id = state.get("job_id", "")
        message = state.get("message", "")
        intent = state.get("intent", "general")

        # Standalone mode: intent == "web_search" → 무조건 검색
        is_standalone = intent == "web_search"

        # 1. 진행 상황 알림 (primary intent일 때만 — enrichment면 UI 간섭 방지)
        if event_publisher is not None and is_standalone:
            await event_publisher.notify_stage(
                task_id=job_id,
                stage="web_search",
                status="started",
                progress=30,
                message="웹 검색 중...",
            )

        # 2. 검색 쿼리 결정
        # - Standalone: 사용자 메시지 그대로 사용
        # - Enrichment: Router가 이미 검색 필요 여부 결정 (confidence/키워드 기반)
        #   → 불필요한 function_call 생략, Agents SDK가 자체적으로 검색 수행
        search_query = message

        # 3. 웹 검색 실행 (Agents SDK WebSearchTool이 검색 여부 자체 판단)
        logger.info(
            "Executing web search",
            extra={
                "job_id": job_id,
                "mode": "standalone" if is_standalone else "enrichment",
                "query": search_query[:50],
            },
        )

        result = await _execute_web_search(
            message=search_query,
            job_id=job_id,
        )

        if result is None:
            logger.warning(
                "Web search returned no results",
                extra={"job_id": job_id},
            )
            if event_publisher is not None and is_standalone:
                await event_publisher.notify_stage(
                    task_id=job_id,
                    stage="web_search",
                    status="failed",
                    result={"error": "검색 결과 없음"},
                )
            return {
                "web_search_results": create_error_context(
                    producer="web_search",
                    job_id=job_id,
                    error="검색 결과를 가져오지 못했습니다.",
                ),
            }

        # 4. 결과를 context 채널에 저장
        if event_publisher is not None and is_standalone:
            await event_publisher.notify_stage(
                task_id=job_id,
                stage="web_search",
                status="completed",
                progress=50,
                result={"result_length": len(result)},
                message="웹 검색 완료",
            )

        logger.info(
            "Web search completed",
            extra={
                "job_id": job_id,
                "result_length": len(result),
                "mode": "standalone" if is_standalone else "enrichment",
            },
        )

        return {
            "web_search_results": create_context(
                data={
                    "context": result,
                    "query": search_query,
                    "mode": "standalone" if is_standalone else "enrichment",
                },
                producer="web_search",
                job_id=job_id,
            ),
        }

    # NodeExecutor로 래핑 (Policy 적용: timeout, retry, circuit breaker)
    executor = NodeExecutor.get_instance()

    async def web_search_node(state: dict[str, Any]) -> dict[str, Any]:
        """LangGraph 노드 (Policy 적용됨)."""
        return await executor.execute(
            node_name="web_search",
            node_func=_web_search_node_inner,
            state=state,
        )

    return web_search_node
